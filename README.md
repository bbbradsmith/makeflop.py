# makeflop.py

Simple file operations for a FAT12 floppy disk image.

See comments at the top of the source file for documentation.

Public domain.

[Patreon](https://www.patreon.com/rainwarrior)

## TwoSide Version ##

***This fork of makeflop.py is modified to favour filling up side-1 of a disk image before side-2, allowing the creation of Atari ST disk images where the files can be separated for use by single and double sided drives.***

Example:
```
	f = Floppy() # create blank special-format disk
	f.add_all("side1\\","") # add side 1 files
	r = f.close_side1() # finish side 1
	assert(r >= 0) # make sure side 1 is not overflowed
	f.add_all("side2\\","SIDE2\\") # add side 2 files to SIDE2 folder
	print(f.boot_info()) # list boot information about disk
	print(f.file_info()) # list files and directories
	f.set_volume_id() # generates a new volume ID
	f.set_volume_label("TWOSIDE") # changes the volume label
	f.save("twoside.st")
```

The default image created by _Floppy()_ is a 720k disk image, 9 sectors per track. Slightly different formatting could be used. The requirement is merely that all of side 1 track 1 be taken up by the boot sector, FAT tables, and root directory. For the 720k version, this limits us to 32 files in the root directory.

The process of preparing the image is to start with the blank special-format image, add all files for side 1, then use _close_side1()_ to finalize the side. After this, add all files for side 2, preferrably in an easily identifiable folder so single sided drive users won't be confused by which files work.

For example, you can create a SIDE2 folder, which will work normally in a double sided drive, and a user with a single sided drive would know to avoid. For the single sided drive, trying to open this folder will create a read error, after which that folder will appear empty.

This works because even when using a single sided drive, TOS will still identify a double sided format disk, and correctly addresses clusters by side. This means that a single sided drive can access any files or directories that are only stored on side 1 clusters of the disk.

# makenib.py

Simple data inspection and extraction for an Apple II NIB disk image. DOS 3.2 and 3.3.

Public domain.
