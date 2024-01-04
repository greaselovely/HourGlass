# VLA
Very Large Array Timelapse Builder

Captures the VLA image from the public webcam every 15 seconds, determines if the file size was the same as the previous one, and if it is, it does not save it (avoid duplicating images).  

It runs in a while loop, displaying the iteration number, the number of images in the current directory and the file size saved, until keyboard interrupt, at which time it creates an mp4 video timelapse of the images.  

We do not delete the images, you'd have to do that manually.  It only builds the time lapse from today's images.  If you forgot to run the timelapse from yesterday, rename all the images to today's date, run the script, and immediately ctrl+c and it will build the timelapse.


`pip install -r requirements.txt`

Run.  You can also update your path, but by default it saves it in a subfolder called VLA under your home directory.
