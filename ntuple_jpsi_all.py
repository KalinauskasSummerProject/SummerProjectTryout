import os

from Configurables import DecayTreeTuple
from Configurables import DaVinci
from DecayTreeTuple.Configuration import *
from PhysConf.Filters import LoKi_Filters
from GaudiConf import IOHelper

# ---------------------------------------------------------------------------
# This is the same options file you already had working, with three changes:
#   * the input files come from filelist.txt (XRootD URLs, nothing downloaded)
#   * which slice of that list to run is set by environment variables, so
#     run_all.py can drive it chunk by chunk
#   * an optional stripping prefilter, which makes the job much faster
# You never need to edit this file by hand - run_all.py sets everything.
# ---------------------------------------------------------------------------

stream = 'Dimuon'
line = 'Bs2MuMuLinesBu2JPsiKFullDSTLine'

filelist = os.environ.get('JPSI_FILELIST', 'filelist.txt')
start = int(os.environ.get('JPSI_START', '0'))
nfiles = int(os.environ.get('JPSI_NFILES', '1'))
outfile = os.environ.get('JPSI_OUT', 'DVntuple_jpsi_part.root')
prefilter = os.environ.get('JPSI_PREFILTER', '1') == '1'

with open(filelist) as handle:
    all_files = [ln.strip() for ln in handle if ln.strip() and not ln.startswith('#')]

chunk = all_files[start:start + nfiles]
if not chunk:
    raise RuntimeError('No input files in %s at offset %d' % (filelist, start))

print('MARKER_CHUNK files %d-%d of %d -> %s'
      % (start, start + len(chunk) - 1, len(all_files), outfile))

# Skip events in which our stripping line did not fire. Saves a lot of time,
# because DaVinci then never unpacks those events.
if prefilter:
    filters = LoKi_Filters(
        STRIP_Code="HLT_PASS_RE('Stripping%sDecision')" % line
    )
    DaVinci().EventPreFilters = filters.filters('Filters')

dtt = DecayTreeTuple('TupleBu2JpsiK')
dtt.Inputs = ['/Event/{0}/Phys/{1}/Particles'.format(stream, line)]
dtt.Decay = '[B+ -> ^(J/psi(1S) -> ^mu+ ^mu-) ^K+]CC'

DaVinci().UserAlgorithms += [dtt]
DaVinci().InputType = 'DST'
DaVinci().TupleFile = outfile
DaVinci().PrintFreq = 500
DaVinci().DataType = '2012'
DaVinci().Simulation = False
DaVinci().Lumi = True
DaVinci().EvtMax = -1

IOHelper().inputFiles(chunk, clear=True)
