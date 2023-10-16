# VLA
Very Large Array Image Download Scripts

Captures the VLA image from the public webcam every 15 seconds, determines if the file size was the same as the previous one, and if it is, it does not save it (avoid duplicating images).  

It runs in a while loop, displaying the number of images it has attempted to save (to do may be to include the number of images not saved and the delta), until keyboard interrupt, at which time it creates an mp4 video timelapse of the images.  We do not delete the images, you'd have to do that manually.


`pip install -r requirements.txt`

Run main.py.  You can also update your path, but by default it saves it in a subfolder called VLA under your home directory.
