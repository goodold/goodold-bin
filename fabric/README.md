Requires Fabric 1.3.3 or newer, http://fabfile.org.
Install Fabric using virtualenv which doesn't require sudo (recommended) or
with sudo: `sudo easy_install pip && sudo pip install fabric`

About installing with virtualenv:
http://stackoverflow.com/questions/4324558/whats-the-proper-way-to-install-pip-virtualenv-and-distribute-for-python

Make sure the bin directory in virtual env directory is added to your path, e.g:
	
	PATH="$HOME/bin/py-env0/bin:$PATH"

Create a ~/.fabricrc and edit it:

    cp ~/bin/goodold-bin/fabric/fabricrc.example ~/.fabricrc

Add the following to your profile if your projects are not located in
`~/Projects` but in e.g `~/Sites` (or optionally specify this in ~/.fabricrc):

    export PROJECT_DIR='~/Sites'