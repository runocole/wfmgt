import os
import sys
from core.wsgi import application

INTERP = os.path.expanduser("/usr/bin/python3")
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

# Set the Django settings module
os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'

# This is what Passenger looks for
application = application