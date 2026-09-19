#!/usr/bin/env python
"""
run_parallel_dtf.py
-------------------
Produces the DecayTreeFitter version of the ntuple. This is the same driver
as run_parallel_all.py - same threading, same resume behaviour - and differs
only in the five configuration constants below, which point it at
ntuple_jpsidtf_all.py and at its own output directories.

    python make_filelist.py                    # once
    python run_parallel_dtf.py --workers 4     # 4 jobs at a time
    python run_parallel_dtf.py --merge-only    # just hadd what exists

Chunks are handed out to a pool of worker threads; each worker launches its
own DaVinci process and waits for it. Finished chunks get a .done marker, so
Ctrl-C and rerun still works exactly as before - in-flight chunks are simply
redone next time.

Each DaVinci process needs roughly 1-1.5 GB of RAM, so keep
    workers x 1.5 GB  <  the "memory=" line in your .wslconfig
Output is per-chunk, so nothing races: ntuples_jpsidtf/DVntuple_jpsi_NNNNNN.root
and logs_jpsidtf/davinci_NNNNNN.log.

Works with either Python 2 or Python 3.

--- What DecayTreeFitter is, and why this second ntuple exists ---------------

The plain ntuple stores m(B+) as reconstructed: the momenta of the two muons
and the kaon are measured independently, and the invariant mass is computed
from them directly. Every measurement error in those momenta propagates
straight into the mass.

DecayTreeFitter (DTF) instead refits the whole decay chain at once, subject to
constraints we know must hold:

  * the two muons came from a common vertex, and so did the J/psi and the kaon
  * the dimuon mass is exactly the known J/psi mass
  * the B+ momentum points back at the primary vertex

It adjusts every track's parameters, within their uncertainties, until those
constraints are satisfied, then rebuilds m(B+) from the adjusted momenta.

Two things follow, and both are visible in the fits:

  * Better resolution. Pinning m(J/psi) removes the dimuon mass uncertainty
    from the result, so the B+ peak narrows considerably.
  * A smaller bias. LHCb's momentum scale in this open data is uncalibrated,
    which shifts reconstructed masses upward by about one part in a thousand.
    Constraining the J/psi to its known mass forces the muon momenta to the
    right scale, so only the kaon's share of the bias survives.

Note that a mass CUT does neither of these. Requiring the measured dimuon mass
to sit near the PDG value only discards candidates; it cannot correct the ones
it keeps, and centring such a window on the PDG value rather than on the
observed peak biases the result. DTF corrects rather than selects.

The cost is CPU time - a vertex refit per candidate - and disk, since the
extra branches roughly double the ntuple size.

The results appear in the ntuple as Bplus_ConsJpsi_*, named after the
'TupleToolDecayTreeFitter/ConsJpsi' instance in ntuple_jpsidtf_all.py. The
originals (Bplus_M and friends) are still there untouched, so one file
supports both the constrained and unconstrained analyses. Two of the new
branches matter when plotting:

  * Bplus_ConsJpsi_status  zero means the fit converged; anything else means
                           it did not, and that candidate must be cut away
  * Bplus_ConsJpsi_M       the refitted mass

Both are ARRAYS, not single numbers: DTF runs once per primary vertex
candidate, and Bplus_ConsJpsi_nPV says how many entries there are. Index 0 is
the best PV, which is why the plotting scripts read Bplus_ConsJpsi_M[0] with
the cut Bplus_ConsJpsi_status[0]==0.

--- A warning if you adapt this ---------------------------------------------

The .done markers are keyed by index into FILELIST, not by filename. If you
point this at a different or reordered file list, old markers will make chunks
look finished that were never run with the new list, and merge() globs *.root
from OUTDIR indiscriminately. Give any new tupling its own OUTDIR, or delete
the markers first.
"""

from __future__ import print_function

import os
import re
import sys
import glob
import time
import argparse
import threading
import subprocess

try:                      # Python 2
    import Queue as queue
except ImportError:       # Python 3
    import queue

# --------------------------------------------------------------------------
# These five lines are the only difference from run_parallel_all.py.
# --------------------------------------------------------------------------
FILELIST = 'filelist.txt'                  # XRootD URLs, one .dst per line
OPTIONS = 'ntuple_jpsidtf_all.py'          # options file WITH the DTF tool
OUTDIR = 'ntuples_jpsidtf'                 # own directory: see the warning above
LOGDIR = 'logs_jpsidtf'
MERGED = 'DVntuple_jpsidtf_all.root'

# Override without editing this file, e.g.
#   export JPSI_DAVINCI="lb-run DaVinci/v45r6 gaudirun.py"
DAVINCI = os.environ.get('JPSI_DAVINCI', 'lb-run DaVinci/v45r8 gaudirun.py').split()
HADD = os.environ.get('JPSI_HADD', 'lb-run DaVinci/v45r8 hadd').split()

EVENT_RE = re.compile(r'Reading Event record\s+(\d+)')

PRINT_LOCK = threading.Lock()
STATS_LOCK = threading.Lock()
ACTIVE_LOCK = threading.Lock()
STOP = threading.Event()
FINISHED = threading.Event()

ACTIVE = {}        # worker -> {'offset':.., 'events':.., 't0':..}
STATUS_LEN = [0]   # width of the status line currently on screen

STATS = {
    'chunks_done': 0,
    'files_done': 0,      # files finished in this session
    'files_skipped': 0,   # files already done before this session
    'events': 0,
    'failed': [],
    'total_files': 0,
    'total_chunks': 0,
    't0': 0.0,
}


# --------------------------------------------------------------------------
def hms(seconds):
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days:
        return '%dd %02dh' % (days, hours)
    return '%02d:%02d:%02d' % (hours, minutes, seconds)


def mmss(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    return '%d:%02d' % (minutes, seconds)


def term_width(default=100):
    try:
        import shutil
        return shutil.get_terminal_size((default, 24)).columns
    except Exception:
        try:
            return int(os.environ.get('COLUMNS', default))
        except ValueError:
            return default


def say(message):
    """Print a permanent line, wiping the live status line out of the way."""
    with PRINT_LOCK:
        if STATUS_LEN[0]:
            sys.stdout.write('\r' + ' ' * STATUS_LEN[0] + '\r')
            STATUS_LEN[0] = 0
        print(message)
        sys.stdout.flush()


def status_line():
    with ACTIVE_LOCK:
        items = sorted(ACTIVE.items())
    if not items:
        return ''
    now = time.time()
    parts = ['w%d %s ev %s' % (worker,
                               '{:,}'.format(info['events']),
                               mmss(now - info['t0']))
             for worker, info in items]
    line = '    running: ' + ' | '.join(parts)
    limit = term_width() - 1
    if len(line) > limit:
        line = line[:limit - 3] + '...'
    return line


def monitor():
    """Redraw the live per-worker event counters roughly twice a second."""
    while not FINISHED.is_set():
        line = status_line()
        if line:
            with PRINT_LOCK:
                pad = max(0, STATUS_LEN[0] - len(line))
                sys.stdout.write('\r' + line + ' ' * pad)
                sys.stdout.flush()
                STATUS_LEN[0] = len(line)
        FINISHED.wait(0.5)
    with PRINT_LOCK:
        if STATUS_LEN[0]:
            sys.stdout.write('\r' + ' ' * STATUS_LEN[0] + '\r')
            sys.stdout.flush()
            STATUS_LEN[0] = 0


def events_from_log(path):
    """Last 'Reading Event record N' in the log, i.e. how far the job got."""
    last = 0
    try:
        with open(path) as handle:
            for line in handle:
                match = EVENT_RE.search(line)
                if match:
                    last = int(match.group(1))
    except IOError:
        pass
    return last


def run_one(worker, offset, nfiles, prefilter):
    """Launch one DaVinci job. Returns True on success."""
    tag = '%06d' % offset
    out = os.path.join(OUTDIR, 'DVntuple_jpsi_%s.root' % tag)
    log = os.path.join(LOGDIR, 'davinci_%s.log' % tag)

    env = os.environ.copy()
    env['JPSI_FILELIST'] = os.path.abspath(FILELIST)
    env['JPSI_START'] = str(offset)
    env['JPSI_NFILES'] = str(nfiles)
    env['JPSI_OUT'] = out
    env['JPSI_PREFILTER'] = '1' if prefilter else '0'

    t0 = time.time()
    events = 0
    with ACTIVE_LOCK:
        ACTIVE[worker] = {'offset': offset, 'events': 0, 't0': t0}

    try:
        try:
            proc = subprocess.Popen(DAVINCI + [OPTIONS],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    env=env,
                                    bufsize=1,
                                    universal_newlines=True)
        except OSError as err:
            say('Could not start "%s" (%s). Run this from the shell where '
                'lb-run works.' % (' '.join(DAVINCI), err))
            STOP.set()
            return False

        with open(log, 'w') as handle:
            for raw in iter(proc.stdout.readline, ''):
                handle.write(raw)
                match = EVENT_RE.search(raw)
                if match:
                    events = int(match.group(1))
                    with ACTIVE_LOCK:
                        if worker in ACTIVE:
                            ACTIVE[worker]['events'] = events
        proc.stdout.close()
        code = proc.wait()
    finally:
        with ACTIVE_LOCK:
            ACTIVE.pop(worker, None)

    took = time.time() - t0
    if not events:
        events = events_from_log(log)

    if code == 0:
        open(out + '.done', 'w').close()
        with STATS_LOCK:
            STATS['chunks_done'] += 1
            STATS['files_done'] += nfiles
            STATS['events'] += events
            done = STATS['files_done'] + STATS['files_skipped']
            elapsed = time.time() - STATS['t0']
            if STATS['files_done']:
                per_file = elapsed / STATS['files_done']
                eta = hms(per_file * (STATS['total_files'] - done))
                rate = '%.1f min/file' % (per_file / 60.0)
            else:
                eta, rate = '--', '--'
            pct = 100.0 * done / max(STATS['total_files'], 1)
            chunks = STATS['chunks_done']
        say('  w%d done files %d-%d in %s (%s events) | %d/%d files %.1f%% '
            '| %s | ETA %s | %d chunks finished'
            % (worker, offset, offset + nfiles - 1, hms(took),
               '{:,}'.format(events), done, STATS['total_files'], pct,
               rate, eta, chunks))
        return True

    with STATS_LOCK:
        pass
    say('  w%d FAILED files %d-%d (exit %s) - see %s'
        % (worker, offset, offset + nfiles - 1, code, log))
    return False


def worker_loop(worker, jobs, prefilter):
    while not STOP.is_set():
        try:
            offset, nfiles = jobs.get_nowait()
        except queue.Empty:
            return
        try:
            say('  w%d start files %d-%d' % (worker, offset, offset + nfiles - 1))
            ok = run_one(worker, offset, nfiles, prefilter)
            if not ok and not STOP.is_set():
                say('  w%d retrying files %d-%d' % (worker, offset, offset + nfiles - 1))
                ok = run_one(worker, offset, nfiles, prefilter)
            if not ok:
                with STATS_LOCK:
                    STATS['failed'].append((offset, nfiles))
        finally:
            jobs.task_done()


def merge(outdir, merged):
    parts = sorted(glob.glob(os.path.join(outdir, '*.root')))
    if not parts:
        print('Nothing to merge.')
        return
    print('\nMerging %d ntuples into %s ...' % (len(parts), merged))
    try:
        code = subprocess.call(HADD + ['-f', merged] + parts)
    except OSError as err:
        print('Could not run hadd (%s).' % err)
        return
    if code == 0:
        size = os.path.getsize(merged) / (1024.0 * 1024.0)
        print('MARKER_MERGED %s  (%.1f MB, from %d parts)' % (merged, size, len(parts)))
    else:
        print('hadd returned %d - check the parts in %s/' % (code, outdir))


# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=4,
                        help='DaVinci jobs to run at once (default 4)')
    parser.add_argument('--files-per-job', type=int, default=5,
                        help='.dst files per DaVinci job (default 5)')
    parser.add_argument('--max-files', type=int, default=0,
                        help='stop after this many .dst files (0 = all)')
    parser.add_argument('--start', type=int, default=0,
                        help='index of the first .dst file to process')
    parser.add_argument('--no-prefilter', action='store_true',
                        help='do not skip events where the stripping line did not fire')
    parser.add_argument('--merge-only', action='store_true',
                        help='just hadd whatever is already in %s/' % OUTDIR)
    args = parser.parse_args()

    if args.merge_only:
        merge(OUTDIR, MERGED)
        return

    if not os.path.exists(FILELIST):
        sys.exit('%s not found - run "python make_filelist.py" first.' % FILELIST)
    with open(FILELIST) as handle:
        files = [ln.strip() for ln in handle if ln.strip() and not ln.startswith('#')]
    if not files:
        sys.exit('%s is empty.' % FILELIST)

    for directory in (OUTDIR, LOGDIR):
        if not os.path.isdir(directory):
            os.makedirs(directory)

    last = len(files) if args.max_files <= 0 else min(len(files), args.start + args.max_files)

    jobs = queue.Queue()
    pending = 0
    skipped_files = 0
    for offset in range(args.start, last, args.files_per_job):
        nfiles = min(args.files_per_job, last - offset)
        marker = os.path.join(OUTDIR, 'DVntuple_jpsi_%06d.root.done' % offset)
        if os.path.exists(marker):
            skipped_files += nfiles
            continue
        jobs.put((offset, nfiles))
        pending += 1

    STATS['total_files'] = last - args.start
    STATS['total_chunks'] = pending
    STATS['files_skipped'] = skipped_files
    STATS['t0'] = time.time()

    print('=' * 72)
    print(' %d .dst files in %s' % (len(files), FILELIST))
    print(' processing files %d-%d  (%d files)' % (args.start, last - 1, STATS['total_files']))
    print(' %d chunks of %d to run, %d files already done' % (pending, args.files_per_job, skipped_files))
    print(' workers: %d    prefilter: %s'
          % (args.workers, 'off' if args.no_prefilter else 'on'))
    print('=' * 72)

    if not pending:
        print('Everything in that range is already done.')
        merge(OUTDIR, MERGED)
        return

    watcher = threading.Thread(target=monitor)
    watcher.daemon = True
    watcher.start()

    threads = []
    for worker in range(1, args.workers + 1):
        thread = threading.Thread(target=worker_loop,
                                  args=(worker, jobs, not args.no_prefilter))
        thread.daemon = True
        thread.start()
        threads.append(thread)
        time.sleep(3)   # stagger the starts so 4 containers don't boot at once

    try:
        while any(t.is_alive() for t in threads):
            time.sleep(0.5)
    except KeyboardInterrupt:
        STOP.set()
        print('\n\nStopping after the jobs now running finish '
              '(Ctrl-C again to kill them outright) ...')
        try:
            while any(t.is_alive() for t in threads):
                time.sleep(0.5)
        except KeyboardInterrupt:
            print('killing.')

    FINISHED.set()
    watcher.join(2.0)

    done = STATS['files_done'] + STATS['files_skipped']
    print('\n' + '=' * 72)
    print('MARKER_DONE %d/%d files (%d this session), %s events, %d failed chunks'
          % (done, STATS['total_files'], STATS['files_done'],
             '{:,}'.format(STATS['events']), len(STATS['failed'])))
    print('total wall time %s' % hms(time.time() - STATS['t0']))
    if STATS['failed']:
        with open('failed_chunks.txt', 'w') as handle:
            for offset, nfiles in STATS['failed']:
                handle.write('%d %d\n' % (offset, nfiles))
        print('failed chunks written to failed_chunks.txt (just rerun to retry them)')
    print('=' * 72)

    merge(OUTDIR, MERGED)


if __name__ == '__main__':
    main()
