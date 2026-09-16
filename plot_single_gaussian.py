"""
plot_single_gaussian.py
-----------------------
Same two-panel layout as plot_double_gaussian.py, but the signal is modelled
as a SINGLE Gaussian. This is the simpler model, and the one to fit first:
it has two fewer parameters, and comparing its chi2/ndf against the double
Gaussian is what tells you whether the second component is earning its place.

How to run:

    lb-run DaVinci/v45r8 python plot_single_gaussian.py                  # operates on 'DVntuple_jpsi_all.root'
    lb-run DaVinci/v45r8 python plot_single_gaussian.py <ntuple_name>    # operates on specified ntuple

The script takes in our created ntuple "DVntuple_jpsi_all.root" and creates
a mass histogram of our rebuilt B^+ particle. The data is then fitted using a single
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

BRANCH = 'Bplus_M' # Change the branch of the stripping line
CUT = ('Kplus_PIDK > 10' # Log-likelihood comparison of K^+ candidates vs pi^+ candidates
       ' && Bplus_FDCHI2_OWNPV > 100' # flight distance significance
       ' && Bplus_IPCHI2_OWNPV < 25' # impact parameter significance
       ' && Bplus_ENDVERTEX_CHI2 < 20') # vertex fit quality, the three tracks must meet at a common point.

# Pad layout. ROOT text sizes are fractions of the PAD height, so fix a target
# size in canvas units and divide by each pad's height fraction.
SPLIT = 0.40
BASE = 0.032
S1 = BASE / (1.0 - SPLIT)
S2 = BASE / SPLIT

fname = sys.argv[1] if len(sys.argv) > 1 else 'DVntuple_jpsi_all.root'
f = ROOT.TFile.Open(fname)
t = f.Get('TupleBu2JpsiK/DecayTree')
if not t or not t.GetEntries():
    sys.exit('No entries found in %s' % fname)

# The following lines need to be adjusted for a different decay:

h = ROOT.TH1F('h', ';m(J/#psi K^{+}) [MeV/c^{2}];Candidates', NBINS, MLO, MHI)
t.Draw('%s>>h' % BRANCH, CUT, 'goff')
h.SetName('J/#psi mass')


# ---------------------------------------------------------------------------
# Model: Gaussian signal + exponential background.
# ROOT builds this from its own named formulas, so the parameters are
#   p0 N, p1 mu, p2 sigma   (gaus)
#   p3 bkg const, p4 bkg slope   (expo)
# ---------------------------------------------------------------------------

fit = ROOT.TF1('fit', 'gaus(0) + expo(3)', MLO, MHI)
fit.SetParNames('N', 'mu', 'sigma', 'bkg const', 'bkg slope')
fit.SetParameters(h.GetMaximum(), 5280.0, 8.0, 7.0, -0.001)
fit.SetParLimits(1, 5250, 5310)
fit.SetParLimits(2, 1, 30)
fit.SetLineColor(ROOT.kBlack)
fit.SetLineWidth(3)
h.Fit(fit, 'R')

mu = fit.GetParameter(1)
mu_err = fit.GetParError(1)
sigma = fit.GetParameter(2)
sigma_err = fit.GetParError(2)

# Components, from the fitted parameters.
bkg = ROOT.TF1('bkg', 'expo', MLO, MHI)
bkg.SetParameters(fit.GetParameter(3), fit.GetParameter(4))
bkg.SetLineColor(ROOT.kRed)
bkg.SetLineStyle(2)
bkg.SetLineWidth(2)

sig = ROOT.TF1('sig', 'gaus', MLO, MHI)
sig.SetParameters(fit.GetParameter(0), mu, sigma)
sig.SetLineColor(ROOT.kBlack)
sig.SetLineWidth(2)

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
leg.AddEntry(fit, 'Single Gaussian + exponential', 'l')
leg.AddEntry(bkg, 'Background component', 'l')
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
zero = ROOT.TLine(MLO, 0, MHI, 0)
zero.SetLineStyle(2)
zero.Draw()

leg2 = ROOT.TLegend(0.62, 0.55, 0.90, 0.97)
leg2.SetBorderSize(1)
leg2.SetFillColor(0)
leg2.SetMargin(0.15)
leg2.SetTextSize(S2 * 0.62)
leg2.AddEntry(h_sub, 'Data with background removed', 'f')
leg2.AddEntry(sig, 'Single Gaussian', 'l')
leg2.AddEntry(ROOT.nullptr, '#chi^2/ndf = %.2f' % (fit.GetChisquare() / fit.GetNDF()), '')
leg2.AddEntry(ROOT.nullptr, 'm(B^{+}) = %.2f #pm %.2f MeV/c^{2}' % (mu, mu_err), '')
leg2.AddEntry(ROOT.nullptr,
              '#sigma = %.2f #pm %.2f MeV/c^{2}' % (sigma, sigma_err), '')
leg2.Draw()

c.SaveAs('Bplus_single_gaussian_magup.png')
show('Bplus_single_gaussian_magup.png') # Remove this line if you don't want to deal with serve_plots.py and show.py files. The script then only saves the image to the working directory

# ---------------------------------------------------------------------------
binw = h.GetBinWidth(1)
n_sig = sig.Integral(mu - 3 * sigma, mu + 3 * sigma) / binw
n_bkg = bkg.Integral(mu - 3 * sigma, mu + 3 * sigma) / binw

print('')
print('MARKER_FIT mass      = %.2f +/- %.2f MeV' % (mu, mu_err))
print('MARKER_FIT sigma     = %.2f +/- %.2f MeV' % (sigma, sigma_err))
print('MARKER_FIT chi2/ndf  = %.2f' % (fit.GetChisquare() / fit.GetNDF()))
M_B = 5279.34
print('MARKER_FIT offset from PDG = %+.2f MeV  (fractional %+.2e)'
      % (mu - M_B, (mu - M_B) / M_B))
