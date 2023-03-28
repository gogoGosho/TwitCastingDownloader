the same as https://github.com/Spicadox/TwitCastingDownloader , except it automatically converts all the downloaded mp4 files into .opus<br>
you must have:
- every req from here: https://github.com/Spicadox/TwitCastingDownloader
- send2trash installed (pip install it)
- ffmpeg (in PATH)

loops over all the mp4s in the directory, converts them one at a time to .opus and then sends them to the trash can. you can obviously just replace the send2trash part with something to delete them outright.

i made this because mp4s are too heavy and i dont have a lot of space

(ive not tested this as a script, i just run the program from vscode, so it might not work as a script idk, if it doesnt work - fix it yourself)
