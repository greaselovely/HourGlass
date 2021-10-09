#!/bin/bash

#
#
#
#

##################################
#
URL="https://public.nrao.edu/wp-content/uploads/temp/vla_webcam_temp.jpg"
#
#
OutPath="${HOME}/VLA"
#
###################################

# Test if the directory exists; if not, create them.
if [[ ! -d $OutPath ]]
    then
		mkdir -p $OutPath
fi

function activity() {
    echo -n "$1"
}

function getVLA() {
    TodayShortDate=$(date +%m%d%Y)
    TodayShortTime=$(date +%H%M%S)
    FileName="vla.$TodayShortDate.$TodayShortTime.jpg"
    curl -sk --connect-timeout 29.01 -# --output "$OutPath/$FileName" "$URL"
}

###########################
### Do Stuff and Things ###

clear
while :
    do
        getVLA
        activity "#"
        sleep 30
done

### Do Stuff and Things ###
###########################
