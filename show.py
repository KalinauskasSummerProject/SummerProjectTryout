"""
show.py
-------
Drop-in helper for the plotting scripts. After saving a canvas, call

    from show import show
    c.SaveAs('Bplus_dg_nodtf.png')
    show('Bplus_dg_nodtf.png')

and the script prints a localhost URL for the file, served by serve_plots.py.
Ctrl-click it in Windows Terminal, or keep the tab open and hit refresh - the
server sends no-cache headers, so a refresh always shows the current file.

Nothing is opened for you. This prints a URL and stops.

Configure with environment variables if your layout differs:

    export PLOT_ROOT=~/data        # directory serve_plots.py is serving
    export PLOT_PORT=8000

Works under Python 2 and 3, because the container's python may be either.

This function was created since images didn't seem to open from my container, but if one 
doesn't face this issue, the file can be ignored entirely, and all instances of the show()
function should be removed from the plot scripts.
"""

from __future__ import print_function

import os

PLOT_ROOT = os.path.abspath(os.path.expanduser(
    os.environ.get('PLOT_ROOT', '~/data')))
PLOT_PORT = os.environ.get('PLOT_PORT', '8000')


def url_for(path):
    """localhost URL for path, or None if it sits outside the served root."""
    path = os.path.abspath(path)
    try:
        rel = os.path.relpath(path, PLOT_ROOT)
    except ValueError:            # different drives, Python 2 on odd paths
        return None
    if rel.startswith('..'):
        return None
    return 'http://localhost:%s/%s' % (PLOT_PORT, rel.replace(os.sep, '/'))


def show(path):
    """Print where to look at a saved plot."""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        print('show: %s does not exist' % path)
        return

    link = url_for(path)
    print('')
    if link:
        print('VIEW  %s' % link)
    else:
        print('VIEW  %s' % path)
        print('      (outside PLOT_ROOT=%s, so no URL - move it there or '
              'set PLOT_ROOT)' % PLOT_ROOT)
