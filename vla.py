
import requests
from time import sleep
from datetime import datetime
import os

##################################
#
URL = "https://public.nrao.edu/wp-content/uploads/temp/vla_webcam_temp.jpg"
#
# Creates a directory path using the home folder and a subdirectory
Home = os.path.expanduser('~')
OutPath = os.path.join(Home, "VLA")
#
###################################

# Test if the directory exists; if not, create them.
if not os.path.exists(OutPath):
    os.makedirs(OutPath)

def activity(char):
    print(char, end="", flush=True)

def getVLA():
    TodayShortDate = datetime.now().strftime("%m%d%Y")
    TodayShortTime = datetime.now().strftime("%H%M%S")
    r = requests.get(URL)
    FileName='vla.' + str(TodayShortDate) + "." + str(TodayShortTime) + ".jpg"
    open(os.path.join(OutPath, FileName), 'wb').write(r.content)

###########################
### Do Stuff and Things ###

while True:
    getVLA()
    activity("#")
    sleep(30)

### Do Stuff and Things ###
###########################
