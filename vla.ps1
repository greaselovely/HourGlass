
#
#
#
#

##################################
#
$URL = "https://public.nrao.edu/wp-content/uploads/temp/vla_webcam_temp.jpg"
#
#
$OutPath = "$env:HOMEDRIVE$env:HOMEPATH\Desktop\VLA"
#
###################################

# Test if the directory exists; if not, create them.
if(!(Test-Path $OutPath)) {
	New-Item -ItemType Directory -Force -Path $OutPath
}
function activity {
		param ($char)
	Write-Host -NoNewLine "$char"
}

function getVLA() {
	$TodayShortDate = (Get-Date -UFormat %m%d%Y)
	$TodayShortTime = (Get-Date -UFormat %H%M%S)
	$FileName="vla.$TodayShortDate.$TodayShortTime.jpg"
	Invoke-WebRequest -uri $URL -Outfile $OutPath\$FileName
}

###########################
### Do Stuff and Things ###

clear
while ($true) {
	getVLA
	activity -char "#"
	Start-Sleep -Seconds 30
}

### Do Stuff and Things ###
###########################
