# B⁺ → J/ψ K⁺ with LHCb 2012 open data

Reconstruction of the decay B⁺ → J/ψ(→ μ⁺μ⁻) K⁺ from publicly released LHCb
Run 1 collision data, from raw stripped DSTs through to a fitted mass peak.

Second-year undergraduate summer project. Everything here runs on a laptop:
the data is streamed from CERN over XRootD rather than downloaded, so the only
large file produced locally is the ntuple.

[B+ mass peak](Bplus_double_gaussian_magup.png)

## Results

| Quantity | Value |
| --- | --- |
| Entries | 533608 |
| m(B⁺), double Gaussian + exponential | 5284.14 MeV/c² |
| σ_eff | 0.04 MeV/c² |
| χ²/ndf, single Gaussian | 9.46 |
| χ²/ndf, double Gaussian | 3.56 |
| PDG m(B⁺) | 5279.34 MeV/c² |

## Data

CERN Open Data Portal, LHCb 2012, Stripping21r0p2, DIMUON stream:

| Record | Polarity | Files |
| --- | --- | --- |
| [28070](https://opendata.cern.ch/record/28070) | MagUp | 4390 |
| [28064](https://opendata.cern.ch/record/28064) | MagDown | 4591 |

Candidates come from the stripping line `Bs2MuMuLinesBu2JPsiKFullDSTLine`.

## Requirements

- LHCb software from CVMFS, accessed with `lb-run DaVinci/v45r8`
- Linux, or WSL2 on Windows (developed on AlmaLinux 9 under WSL2)
- No local copy of the data: the DSTs are read over XRootD

Setting up CVMFS is the hardest part of getting started. One should ask their supervisor for a guide if possible.

## Running the analysis

Build the list of input files (writes `filelist.txt`):

```bash
python make_filelist.py 28070
mv filelist.txt filelist_magup.txt
```

Produce the ntuples. This is the long step — a few days of wall time for the
full sample on four cores. It is resumable: each finished chunk leaves a
`.done` marker, so an interrupted run picks up where it stopped.

```bash
python run_parallel_all.py --workers 4
python run_parallel_all.py --workers 4 --max-files 10   # short smoke test first
python run_parallel_all.py --merge-only                 # just re-merge what exists
```

Fit and plot:

```bash
lb-run DaVinci/v45r8 python plot_single_gaussian.py DVntuple_jpsi_all.root
lb-run DaVinci/v45r8 python plot_double_gaussian.py DVntuple_jpsi_all.root
```

## What each script does

| File | Purpose |
| --- | --- |
| `make_filelist.py` | Fetches the XRootD URLs for an open data record |
| `ntuple_jpsi_all.py` | DaVinci options file: DSTs in, flat ntuple out |
| `run_parallel_all.py` | Runs several DaVinci jobs at once, then merges |
| `plot_single_gaussian.py` | Gaussian + exponential fit to the B⁺ peak |
| `plot_double_gaussian.py` | Narrow core + wide component, for the resolution mixture |
| `show.py`, `serve_plots.py` | View plots in a browser without copying files out of WSL |

`ntuple_jpsi_all.py` is never run directly. `run_parallel_all.py` passes it to
`gaudirun.py` once per chunk, handing over the file range in environment
variables.

## Adapting this to a different decay

Change `stream` and `line` in `ntuple_jpsi_all.py` to your stripping line, and
`dtt.Decay` to its decay descriptor. Then in `run_parallel_all.py` update
`FILELIST`, `OPTIONS`, `OUTDIR`, `LOGDIR` and `MERGED`, plus the per-chunk
filename inside `run_one` and the matching marker pattern in `main`.

Two things that bite:

- Give a new tupling its own `OUTDIR`. Stale `.done` markers make every chunk
  look finished, and `merge()` globs `*.root` from that directory, so two
  tuplings sharing one would be silently merged into each other.
- Branch prefixes follow the decay descriptor, not reality. The hadron's
  branches are `Kplus_*` whether or not the track is a kaon, which is why
  `Kplus_PIDK` is worth cutting on.

If the line writes to microDST rather than full DST, set
`DaVinci().RootInTES` and give `dtt.Inputs` the relative path instead.

## Notes

The data is uncalibrated for momentum scale, so the reconstructed masses sit
roughly 5 MeV above the PDG values. Constraining the J/ψ mass with
DecayTreeFitter improves the resolution considerably.

Ntuples, logs and per-chunk outputs are not tracked — see `.gitignore`. Rerun
the pipeline to regenerate them.

## License

Code in this repository is released under the MIT License (see `LICENSE`).
The underlying LHCb data belongs to CERN and is distributed under the terms
given on the open data record pages.
