"""
plot_bplus_dg_dtf.py
--------------------
Same two-panel layout as before, but the signal is modelled as TWO Gaussians
sharing a mean: a narrow core plus a wider component. This is used when the error 
bars on each data point are not equal and follow some distribution themselves.
In this case, a single-Gaussian fit is insufficient, and provides a worse 
chi2/ndf value.

This version reads the DecayTreeFitter ntuple. DTF refits each candidate with
the J/psi mass constrained to its PDG value and the decay products required to
come from a common vertex, then rebuilds m(B+) from the adjusted momenta. Two
consequences: the mass resolution improves, and the muons' share of the
momentum-scale bias is removed, so the offset from the PDG B+ mass should be
noticeably smaller than in the unconstrained fit.

How to run:

    lb-run DaVinci/v45r8 python plot_bplus_dg_dtf.py                  # operates on 'DVntuple_jpsidtf_all.root'
    lb-run DaVinci/v45r8 python plot_bplus_dg_dtf.py <ntuple_name>    # operates on specified ntuple

The script takes in our created ntuple "DVntuple_jpsidtf_all.root" and creates
a mass histogram of our rebuilt B^+ particle. The data is then fitted using a double
Gaussian distribution + an exponential background, to determine what the most probable
mass of the particle is.
"""

import sys
import ROOT
from show import show # Remove this line if you don't want to deal with serve_plots.py and show.py files. The script then only saves the image to the working directory

ROOT.gROOT.SetBatch(True)
ROOT.gStyle.SetOptStat(0)

MLO, MHI = 5200.0, 5350.0 # Change x axis limits
BINW = 1.0 # Change bin width
NBINS = int(round((MHI - MLO) / BINW))   

# The DTF-refitted mass. [0] picks the best primary vertex: DecayTreeFitter
# runs once per PV candidate and stores the results as an array, ordered with
# the best PV first. Bplus_ConsJpsi_nPV says how many entries there are.
BRANCH = 'Bplus_ConsJpsi_M[0]' # Change the branch of the stripping line
CUT = ('Bplus_ConsJpsi_status[0]==0'         # DTF converged for this candidate
       ' && Kplus_PIDK > 2'                  # Log-likelihood comparison of K^+ candidates vs pi^+ candidates
       ' && Bplus_DIRA_OWNPV > 0.9999'       # The cosine of the angle between the B⁺ momentum vector and the line from the primary vertex to its decay vertex.
       ' && Bplus_FDCHI2_OWNPV > 100'        # flight distance significance
       ' && Bplus_IPCHI2_OWNPV < 25'         # impact parameter significance
       ' && Bplus_ENDVERTEX_CHI2 < 20'       # vertex fit quality, the three tracks must meet at a common point.
       ' && abs(J_psi_1S_MM - 3096.9) < 25') # Mass distribution around the known Jpsi value     

# The J/psi mass window from the unconstrained version is deliberately absent:
# DTF fixes m(J/psi) exactly, so cutting on the unconstrained J_psi_1S_MM would
# only throw candidates away, and centring that window on the PDG value biases
# the result low. Uncomment for a like-for-like comparison with the
# unconstrained fit, centred on the OBSERVED J/psi peak, not the PDG value:
# CUT += ' && abs(J_psi_1S_MM - 3099.4) < 10'

# Pad layout. ROOT text sizes are fractions of the PAD height, so fix a target
# size in canvas units and divide by each pad's height fraction.
SPLIT = 0.40
BASE = 0.032
S1 = BASE / (1.0 - SPLIT)
S2 = BASE / SPLIT

fname = sys.argv[1] if len(sys.argv) > 1 else 'DVntuple_jpsidtf_all.root'
f = ROOT.TFile.Open(fname)
if not f or f.IsZombie():
    sys.exit('Could not open %s' % fname)
t = f.Get('TupleBu2JpsiK/DecayTree')
if not t or not t.GetEntries():
    sys.exit('No entries found in %s' % fname)

# The following lines need to be adjusted for a different decay:

h = ROOT.TH1F('h', ';m(J/#psi K^{+}) [MeV/c^{2}];Candidates', NBINS, MLO, MHI) 
t.Draw('%s>>h' % BRANCH, CUT, 'goff')
h.SetName('J/#psi mass')

if h.Integral(1, h.GetNbinsX()) <= 0:
    sys.exit('Nothing passed the cut - does %s have the ConsJpsi branches?' % fname)


# ---------------------------------------------------------------------------
# Model: (core Gaussian + frac * wide Gaussian) + exponential background.
# Both Gaussians share the mean p1; the wide one has width p2*p4.
# ---------------------------------------------------------------------------

def two_gaus_expo(x, p):
    core = ROOT.TMath.Gaus(x[0], p[1], p[2])
    wide = ROOT.TMath.Gaus(x[0], p[1], p[2] * p[4])
    return p[0] * (core + p[3] * wide) + ROOT.TMath.Exp(p[5] + p[6] * x[0])


def two_gaus_only(x, p):
    core = ROOT.TMath.Gaus(x[0], p[1], p[2])
    wide = ROOT.TMath.Gaus(x[0], p[1], p[2] * p[4])
    return p[0] * (core + p[3] * wide)


fit = ROOT.TF1('fit', two_gaus_expo, MLO, MHI, 7)
fit.SetParNames('N', 'mu', 'sigma1', 'frac', 'ratio', 'bkg const', 'bkg slope')
fit.SetParameters(h.GetMaximum(), 5280.0, 8.0, 0.3, 2.0, 7.0, -0.001)
fit.SetParLimits(1, 5250, 5310)
fit.SetParLimits(2, 1, 30)
fit.SetParLimits(3, 0.0, 2.0)     # how much wide component relative to core
fit.SetParLimits(4, 1.0, 5.0)     # wide sigma is this multiple of the core
fit.SetLineColor(ROOT.kBlack)
fit.SetLineWidth(3)
h.Fit(fit, 'R')

mu = fit.GetParameter(1)
mu_err = fit.GetParError(1)
s1 = fit.GetParameter(2)
s1_err = fit.GetParError(2)
frac = fit.GetParameter(3)
ratio = fit.GetParameter(4)
s2 = s1 * ratio

# Effective width of the mixture - this is the number to quote and to compare
# against a single-Gaussian sigma, NOT sigma1 on its own.
w1 = 1.0 / (1.0 + frac)                       # weight of the core
sigma_eff = (w1 * s1 ** 2 + (1.0 - w1) * s2 ** 2) ** 0.5

# Components, from the fitted parameters.
bkg = ROOT.TF1('bkg', 'expo', MLO, MHI)
bkg.SetParameters(fit.GetParameter(5), fit.GetParameter(6))
bkg.SetLineColor(ROOT.kRed)
bkg.SetLineStyle(2)
bkg.SetLineWidth(2)

sig = ROOT.TF1('sig', two_gaus_only, MLO, MHI, 5)
for i in range(5):
    sig.SetParameter(i, fit.GetParameter(i))
sig.SetLineColor(ROOT.kBlack)
sig.SetLineWidth(2)

# The two components separately, to show the mixture in the residual panel.
core_fn = ROOT.TF1('core_fn', 'gaus', MLO, MHI)
core_fn.SetParameters(fit.GetParameter(0), mu, s1)
core_fn.SetLineColor(ROOT.kBlue + 1)
core_fn.SetLineStyle(2)
core_fn.SetLineWidth(2)

wide_fn = ROOT.TF1('wide_fn', 'gaus', MLO, MHI)
wide_fn.SetParameters(fit.GetParameter(0) * frac, mu, s2)
wide_fn.SetLineColor(ROOT.kGreen + 2)
wide_fn.SetLineStyle(2)
wide_fn.SetLineWidth(2)

# Data minus background, bin by bin.
h_sub = h.Clone('h_sub')
h_sub.SetDirectory(0)
h_sub.GetListOfFunctions().Clear()
for i in range(1, h_sub.GetNbinsX() + 1):
    h_sub.SetBinContent(i, h.GetBinContent(i) - bkg.Eval(h_sub.GetBinCenter(i)))

# ---------------------------------------------------------------------------
c = ROOT.TCanvas('c', 'Bplus mass', 1200, 900)

pad1 = ROOT.TPad('pad1', '', 0, SPLIT, 1, 1.0)
pad1.SetBottomMargin(0.03)
pad1.SetGrid()
pad1.Draw()

pad2 = ROOT.TPad('pad2', '', 0, 0.0, 1, SPLIT)
pad2.SetTopMargin(0.03)
pad2.SetBottomMargin(0.30)
pad2.SetGrid()
pad2.Draw()

# ---- top pad ----
pad1.cd()
h.SetLineColor(ROOT.kBlue - 7)
h.SetLineWidth(2)
h.SetFillColor(ROOT.kBlue - 10)
h.SetFillStyle(1001)
h.GetXaxis().SetLabelSize(0)
h.GetXaxis().SetTitleSize(0)
h.GetYaxis().SetTitleSize(S1)
h.GetYaxis().SetLabelSize(S1 * 0.88)
h.GetYaxis().SetTitleOffset(0.88)
h.GetYaxis().CenterTitle()
h.Draw()
bkg.Draw('same')

leg = ROOT.TLegend(0.62, 0.55, 0.90, 0.90)
leg.SetBorderSize(1)
leg.SetFillColor(0)
leg.SetMargin(0.12)
leg.SetTextSize(S1 * 0.68)
leg.AddEntry(h, 'LHCb 2012 open data', 'f')
leg.AddEntry(fit, 'Double Gaussian + exponential', 'l')
leg.AddEntry(bkg, 'Background component', 'l')
leg.AddEntry(ROOT.nullptr, 'J/#psi mass constrained (DTF)', '')
leg.AddEntry(ROOT.nullptr, 'Nr. of entries = %d' % h.GetEntries(), '')
leg.Draw()

# ---- bottom pad ----
pad2.cd()
h_sub.SetTitle('')
h_sub.SetFillStyle(1001)
h_sub.SetFillColor(ROOT.kBlue - 10)
h_sub.SetLineColor(ROOT.kBlue - 7)
h_sub.SetLineWidth(1)
h_sub.SetMarkerStyle(20)
h_sub.SetMarkerSize(0.4)
h_sub.SetMarkerColor(ROOT.kBlack)
h_sub.GetXaxis().SetTitle('m(J/#psi K^{+}) [MeV/c^{2}]')
h_sub.GetYaxis().SetTitle('Background removed')
h_sub.GetXaxis().SetTitleSize(S2)
h_sub.GetXaxis().SetLabelSize(S2 * 0.88)
h_sub.GetXaxis().SetTitleOffset(1.25)
h_sub.GetYaxis().SetTitleSize(S2)
h_sub.GetYaxis().SetLabelSize(S2 * 0.88)
h_sub.GetYaxis().SetTitleOffset(0.58)
h_sub.GetYaxis().SetNdivisions(505)
h_sub.GetYaxis().CenterTitle()
h_sub.SetMaximum(1.30 * h_sub.GetMaximum())
h_sub.Draw()
sig.Draw('same')
core_fn.Draw('same')
wide_fn.Draw('same')
zero = ROOT.TLine(MLO, 0, MHI, 0)
zero.SetLineStyle(2)
zero.Draw()

leg2 = ROOT.TLegend(0.62, 0.55, 0.90, 0.97)
leg2.SetBorderSize(1)
leg2.SetFillColor(0)
leg2.SetMargin(0.15)
leg2.SetTextSize(S2 * 0.62)
leg2.AddEntry(h_sub, 'Data with background removed', 'f')
leg2.AddEntry(sig, 'Double Gaussian', 'l')
leg2.AddEntry(core_fn, 'core, #sigma_{1} = %.2f' % s1, 'l')
leg2.AddEntry(wide_fn, 'wide, #sigma_{2} = %.2f' % s2, 'l')
leg2.AddEntry(ROOT.nullptr, '#chi^2/ndf = %.2f' % (fit.GetChisquare() / fit.GetNDF()), '')
leg2.AddEntry(ROOT.nullptr, 'm(B^{+}) = %.2f #pm %.2f MeV/c^{2}' % (mu, mu_err), '')
leg2.AddEntry(ROOT.nullptr,
              '#sigma_{eff} = %.2f MeV/c^{2}' % sigma_eff, '')
leg2.Draw()

c.SaveAs('Bplus_dg_dtf.png')
show('Bplus_dg_dtf.png') # Remove this line if you don't want to deal with serve_plots.py and show.py files. The script then only saves the image to the working directory

# ---------------------------------------------------------------------------
binw = h.GetBinWidth(1)
n_sig = sig.Integral(mu - 3 * sigma_eff, mu + 3 * sigma_eff) / binw
n_bkg = bkg.Integral(mu - 3 * sigma_eff, mu + 3 * sigma_eff) / binw

print('')
print('MARKER_FIT mass      = %.2f +/- %.2f MeV' % (mu, mu_err))
print('MARKER_FIT sigma_eff = %.2f MeV' % sigma_eff)
print('MARKER_FIT chi2/ndf  = %.2f' % (fit.GetChisquare() / fit.GetNDF()))
M_B = 5279.34
print('MARKER_FIT offset from PDG = %+.2f MeV  (fractional %+.2e)'
      % (mu - M_B, (mu - M_B) / M_B))
