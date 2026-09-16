"""
ntuple_jpsi_all.py
------------------
DaVinci options file: reads LHCb 2012 open data .dst files and writes a flat
ROOT ntuple of B+ -> J/psi(-> mu+ mu-) K+ candidates.
 
You do not run this file directly. It is handed to gaudirun.py, which is what
actually starts DaVinci:
 
    lb-run DaVinci/v45r8 gaudirun.py ntuple_jpsi_all.py
 
and in practice run_parallel_all.py does that for you, once per chunk of
input files. An "options file" in the Gaudi framework is not a script that
does work - it is Python that *configures* a set of C++ algorithms, and the
event loop only starts after this file has finished executing.
 
Which files to read is passed in through environment variables rather than
command-line arguments, because gaudirun.py owns the command line. That is
the only reason this file looks different from a standard DaVinci example.
"""


import os

from Configurables import DecayTreeTuple
from Configurables import DaVinci
from DecayTreeTuple.Configuration import *
from PhysConf.Filters import LoKi_Filters
from GaudiConf import IOHelper

stream = 'Dimuon' # Change this part to match the descriptors of your decay
line = 'Bs2MuMuLinesBu2JPsiKFullDSTLine' # Change this part to match the descriptors of your decay

filelist = os.environ.get('JPSI_FILELIST', 'filelist.txt') # Rename this part to match your decay
start = int(os.environ.get('JPSI_START', '0')) # Rename this part to match your decay
nfiles = int(os.environ.get('JPSI_NFILES', '1')) # Rename this part to match your decay
outfile = os.environ.get('JPSI_OUT', 'DVntuple_jpsi_part.root') # Rename this part to match your decay
prefilter = os.environ.get('JPSI_PREFILTER', '1') == '1' # Rename this part to match your decay

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

dtt = DecayTreeTuple('TupleBu2JpsiK') # Change this part to match the descriptors of your decay
dtt.Inputs = ['/Event/{0}/Phys/{1}/Particles'.format(stream, line)] # Doesn't need changing unless you are analyzing .mdst files as well as .dst ones.
dtt.Decay = '[B+ -> ^(J/psi(1S) -> ^mu+ ^mu-) ^K+]CC' # Change this part to match the descriptors of your decay

# The following lines shouldn't need changing if you are working with 2012 run-1 data:

DaVinci().UserAlgorithms += [dtt]
DaVinci().InputType = 'DST'
DaVinci().TupleFile = outfile
DaVinci().PrintFreq = 500
DaVinci().DataType = '2012'
DaVinci().Simulation = False
DaVinci().Lumi = True
DaVinci().EvtMax = -1

IOHelper().inputFiles(chunk, clear=True)
