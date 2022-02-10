#!/usr/bin/env python3
#
# makeflop.py
# Version 3
# Brad Smith, 2019
# http://rainwarrior.ca
#
# Simple file operations for a FAT12 floppy disk image.
# Public domain.

# TwoSide Fork
# This favours allocating new clusters on side 1 first,
# allowing the creation of Atari ST disks where the files can be separated
# for use by single and double sided drives.

import sys
assert sys.version_info[0] == 3, "Python 3 required."

import struct
import datetime
import os

class Floppy:
    """
    Simple file operations for a FAT12 floppy disk image.

    Floppy() - creates a blank DOS formatted 1.44MB disk.
    Floppy(data) - parses a disk from a given array of bytes.
    .open(filename) - loads a file and returns a Floppy from its data.
    .save(filename) - saves the disk image to a file.
    .flush() - Updates the .data member with any pending changes.
    .data - A bytearray of the disk image.

    .free_side1() - Returns clusters free on side 1.
    .close_side1() - Reserves all remaining clusters on side 1. Prints and returns count of clusters reserved.

    .files() - Returns a list of strings, each is a file or directory. Directories end with a backslash.
    .delete_path(path) - Deletes a file or directory (recursive).
    .add_dir_path(path) - Creates a new empty directory, if it does not already exist (recursive). Returns cluster of directory, or -1 if failed.
    .add_file_path(path,data) - Creates a new file (creating directory if needed) with the given data. Returns False if failed.
    .extract_file_path(path) - Returns a bytearray of the file at the given path, None if not found.
    .set_volume_id(id=None) - Sets the 32-bit volume ID. Use with no arguments to generate ID from current time.
    .set_volume_label(label) - Sets the 11-character volume label.

    .boot_info() - Returns a string displaying boot sector information.
    .fat_info() - Returns a very long string of all 12-bit FAT entries.
    .files_info() - Returns a string displaying the files() list.

    .add_all(path,prefix) - Adds all files from local path to disk (uppercased). Use prefix to specify a target directory. Returns False if any failed.
    .extract_all(path) - Dumps entire contents of disk to local path.

    .find_path(path) - Returns a Floppy.FileEntry.
    FileEntry.info() - Returns and information string about a FileEntry.

    This class provides some basic interface to a FAT12 floppy disk image.
    Some things are fragile, in particular filenames that are too long,
    or references to clusters outside the disk may cause exceptions.
    The FAT can be accessed directly with some internal functions (see implementation)
    and changes will be applied to the stored .data image with .flush().

    Example:
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
    """

    EMPTY = 0xE5 # incipit value for an empty directory entry

    def _filestring(s, length):
        """Creates an ASCII string, padded to length with spaces ($20)."""
        b = bytearray(s.encode("ASCII"))
        b = b + bytearray([0x20] * (length - len(b)))
        if len(b) != length:
            raise self.Error("File string '%s' too long? (%d != %d)" % (s,len(b),length))
        return b

    class Error(Exception):
        """Floppy has had an error."""
        pass
    
    class FileEntry:
        """A directory entry for a file."""

        def __init__(self, data=None, dir_cluster=-1, dir_index=-1):
            """Unpacks a 32 byte directory entry into a FileEntry structure."""
            if data == None:
                data = bytearray([Floppy.EMPTY]+([0]*31))
            self.data = bytearray(data)
            self.path = ""
            self.incipit = data[0]
            if self.incipit != 0x00 and self.incipit != Floppy.EMPTY:
                filename = data[0:8].decode("ASCII")
                filename = filename.rstrip(" ")
                extension = data[8:11].decode("ASCII")
                extension = extension.rstrip(" ")
                self.path = filename
                if len(extension) > 0:
                    self.path = self.path + "." + extension
            block = struct.unpack("<BHHHHHHHHL",data[11:32])
            self.attributes = block[0]
            self.write_time = block[6]
            self.write_date = block[7]
            self.cluster = block[8]
            self.size = block[9]
            self.dir_cluster = dir_cluster
            self.dir_index = dir_index

        def compile(self):
            """Commits any changed data to the entry, rebuilds and returns the 32 byte structure."""
            filename = ""
            extension = ""
            period = self.path.find(".")
            if (period >= 0):
                filename = self.path[0:period]
                extension = self.path[period+1:]
            else:
                filename = self.path
            if self.incipit != 0x00 and self.incipit != 0xEF:
                self.data[0:8] = Floppy._filestring(filename,8)
                self.data[8:11] = Floppy._filestring(extension,3)
            else:
                self.data[0] = self.incipit
            self.data[11] = self.attributes
            self.data[22:32] = bytearray(struct.pack("<HHHL",
                self.write_time,
                self.write_date,
                self.cluster,
                self.size))
            return bytearray(self.data)

        def info(self):
            """String of information about a FileEntry."""
            s = ""
            s += "Path: [%s]\n" % self.path
            s += "Incipit: %02X\n" % self.incipit
            s += "Attributes: %02X\n" % self.attributes
            s += "Write: %04X %04X\n" % (self.write_date, self.write_time)
            s += "Cluster: %03X\n" % self.cluster
            s += "Size: %d bytes\n" % self.size
            s += "Directory: %03X, %d\n" % (self.dir_cluster, self.dir_index)
            return s

        def fat_time(year, month, day, hour, minute, second):
            """Builds a FAT12 date/time entry."""
            date = ((year - 1980) << 9) | ((month) << 5) | day
            time = (hour << 11) | (minute << 5) | (second >> 1)
            return (date, time)

        def fat_time_now():
            """Builds the current time as a FAT12 date/time entry."""
            now = datetime.datetime.now()
            return Floppy.FileEntry.fat_time(now.year, now.month, now.day, now.hour, now.minute, now.second)

        def set_name(self,s):
            """Sets the filename and updates incipit."""
            self.path = s
            self.incipit = Floppy._filestring(s,12)[0]

        def set_now(self):
            """Updates modified date/time to now."""
            (date,time) = Floppy.FileEntry.fat_time_now()
            self.write_date = date
            self.write_time = time
            
        def new_file(name):
            """Generate a new file entry."""
            e = Floppy.FileEntry()
            e.set_name(name)
            e.set_now()
            e.attributes = 0x00
            return e

        def new_dir(name):
            """Generate a new subdirectory entry."""
            e = Floppy.FileEntry()
            e.set_name(name)
            e.set_now()
            e.attributes = 0x10
            return e

        def new_volume(name):
            """Generate a new volume entry."""
            e = Floppy.FileEntry()
            if len(name) > 8:
                name = name[0:8] + "." + name[8:]
            e.set_name(name)
            e.set_now()
            e.attributes = 0x08
            return e

        def new_terminal():
            """Generate a new directory terminating entry."""
            e = Floppy.FileEntry()
            e.incipit = 0x00
            return e
            
    # special formatted 720k Atari ST floppy
    blank_floppy = [ # boot sector, 2xFAT, 32-entry root completely fill side 1 track 1, E5 fill
        0x00,0x00,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x91,0xE9,0x6C,0x00,0x02,0x02,0x01,0x00,
        0x02,0x20,0x00,0xA0,0x05,0xF9,0x03,0x00,0x09,0x00,0x02,0x00,0x00,0x00,0x4E,0x4E,
        0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,
        0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0xF5,0xF5,0xF5,0xFE,0x4F,0x01,0x01,0x02,
        0xF7,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,
        0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x4E,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0xF5,0xF5,0xF5,0xFB,0xE5,0xE5,0xE5,0xE5,0xE5,0xE5,0xE5,0xE5,0xE5, ] + \
        ([0xE5,]*(23*16)) + [ \
        0xE5,0xE5,0xE5,0xE5,0xE5,0xE5,0xE5,0xE5,0xE5,0xE5,0xE5,0xE5,0xE5,0xE5,0xD6,0x37, ] + \
        [0xF7,0xFF,0xFF] + ([0]*(0x600-3)) + \
        [0xF7,0xFF,0xFF] + ([0]*(0x600-3)) + \
        [0]*(32*32) + \
        [0xE5] * (0xC0000-0x01200)

    def __init__(self,data=blank_floppy):
        """Create Floppy() instance from image bytes, or pre-formatted blank DOS floppy by default."""
        self.data = bytearray(data)
        self._boot_open()
        self._fat_open()

    def _boot_open(self):
        """Parses the boot sector."""
        if (len(self.data) < 38):
            raise self.Error("Not enough data in image for boot sector. (%d bytes)" % len(data))
        boot = struct.unpack("<HBHBHHBHHH",self.data[11:28])
        self.sector_size = boot[0]
        self.cluster_sects = boot[1]
        self.reserved_sects = boot[2]
        self.fat_count = boot[3]
        self.root_max = boot[4]
        self.sectors = boot[5]
        self.fat_sects = boot[7]
        self.track_sects = boot[8]
        self.heads = boot[9]
        self.volume_id = 0
        self.volume_label = ""
        if self.data[38] == 0x29 and len(self.data) >= 54:
            self.volume_id = struct.unpack("<L",self.data[39:43])[0]
            self.volume_label = self.data[43:54].decode("ASCII").rstrip(" ")
        if (self.sectors * self.sector_size) > len(self.data):
            raise self.Error("Not enough data to contain %d x %d byte sectors? (%d bytes)" %
                             (self.sectors, self.sector_size, len(self.data)))
        self.root = self.sector_size * (self.reserved_sects + (self.fat_count * self.fat_sects))
        root_sectors = ((self.root_max * 32) + (self.sector_size-1)) // self.sector_size # round up to fill sector
        self.cluster2 = self.root + (self.sector_size * root_sectors)
        self.cluster_limit = ((self.sectors - (self.cluster2 // self.sector_size)) // self.cluster_sects) + 2
        # TwoSide Fork
        if self.heads != 2:
            print(self.boot_info())
            raise self.error("TwoSide Mod of makeflop.py works only on double-sided media.")
        if self.cluster2 != (self.sector_size * self.track_sects):
            print(self.boot_info())
            raise self.error("TwoSide Mod of makeflop.py expects root sectors to extend to end of side 1 track 1.")

    def _boot_flush(self):
        """Commits changes to the boot sector."""
        boot = struct.pack("<HBHBHHBHHH",
            self.sector_size,
            self.cluster_sects,
            self.reserved_sects,
            self.fat_count,
            self.root_max,
            self.sectors,
            self.data[21],
            self.fat_sects,
            self.track_sects,
            self.heads)
        self.data[11:28] = bytearray(boot)
        if self.data[38] == 0x29 and len(self.data) >= 54:
            self.data[39:43] = bytearray(struct.pack("<L",self.volume_id))
            self.data[43:54] = Floppy._filestring(self.volume_label,11)

    def boot_info(self):
        """String of information about the boot sector."""
        s = ""
        s += "Volume Label: [%s]\n" % self.volume_label
        s += "Volume ID: %04X\n" % self.volume_id
        s += "Sector size: %d bytes\n" % self.sector_size
        s += "Cluster size: %d sectors\n" % self.cluster_sects
        s += "Reserved sectors: %d\n" % self.reserved_sects
        s += "Number of FATs: %d\n" % self.fat_count
        s += "Maximum root entries: %d\n" % self.root_max
        s += "Total sectors: %d\n" % self.sectors
        s += "FAT size: %d sectors\n" % self.fat_sects
        s += "Track size: %d sectors\n" % self.track_sects
        s += "Heads: %d\n" % self.heads
        s += "Root directory: %08X\n" % self.root
        s += "Cluster 2: %08X\n" % self.cluster2
        s += "Total clusters: %d\n" % (self.cluster_limit-2)
        return s

    def _fat_open(self):
        """Parses the FAT table."""
        fat_start = self.reserved_sects * self.sector_size
        fat_sects = self.fat_sects * self.sector_size
        fat_end = fat_start + fat_sects
        # make sure they're in the image
        if (self.sectors < (self.reserved_sects + (self.fat_count * self.fat_sects))):
            raise self.Error("Not enough sectors to contain %d + %d x %d FAT tables? (%d sectors)" %
                            (self.reserved_sects, self.fat_count, self.fat_sects, self.sectors))
        if (self.fat_count < 1) or (self.fat_sects < 1):
            raise self.Error("No FAT tables? (%d x %d FAT sectors)" %
                             (self.fat_count, self.fat_sects))        
        # verify FAT tables match
        for i in range(1,self.fat_count):
            fat2_start = fat_start + (fat_sects * i)
            fat2_end = fat2_start + fat_sects
            if self.data[fat_start:fat_end] != self.data[fat2_start:fat2_end]:
                raise self.Error("FAT mismatch in table %d." % i)
        # read FAT 0
        self.fat = []
        e = fat_start
        while (e+2) <= fat_end:
            entry = 0
            if (len(self.fat) & 1) == 0:
                entry = self.data[e+0] | ((self.data[e+1] & 0x0F) << 8)
                e += 1
            else:
                entry = ((self.data[e+0] & 0xF0) >> 4) | (self.data[e+1] << 4)
                e += 2
            self.fat.append(entry)

    def _fat_flush(self):
        """Commits changes to the FAT table."""
        fat_start = self.reserved_sects * self.sector_size
        fat_sects = self.fat_sects * self.sector_size
        fat_end = fat_start + fat_sects
        # build FAT 0
        e = self.reserved_sects * self.sector_size
        for i in range(len(self.fat)):
            entry = self.fat[i]
            if (i & 1) == 0:
                self.data[e+0] = entry & 0xFF
                self.data[e+1] = (self.data[e+1] & 0xF0) | ((entry >> 8) & 0x0F)
                e += 1
            else:
                self.data[e+0] = (self.data[e+0] & 0x0F) | ((entry << 4) & 0xF0)
                self.data[e+1] = (entry >> 4) & 0xFF
                e += 2
        # copy to all tables
        for i in range(1,self.fat_count):
            fat2_start = fat_start + (fat_sects * i)
            fat2_end = fat2_start + fat_sects
            self.data[fat2_start:fat2_end] = self.data[fat_start:fat_end]

    def fat_info(self):
        """String of information about the FAT."""
        per_line = 18
        s = ""
        for i in range(len(self.fat)):
            if (i % per_line) == 0:
                s += "%03X: " % i
            if (i % per_line) == (per_line // 2):
                s += "  " # extra space to mark 16
            s += " %03X" % self.fat[i]
            if (i % per_line) == (per_line - 1):
                s += "\n"
        return s

    def _cluster_offset(self, cluster):
        """Image offset of a FAT indexed logical cluster."""
        if cluster < 2:
            return self.root
        return self.cluster2 + (self.sector_size * self.cluster_sects * (cluster-2))

    def _read_chain(self, cluster, size):
        data = bytearray()
        """Returns up to size bytes from a chain of clusters starting at cluster."""
        while cluster < 0xFF0:
            offset = self._cluster_offset(cluster)
            #print("read_chain(%03X,%d) at %08X" % (cluster,size,offset))
            if cluster < 2:
                return data + bytearray(self.data[self.root:self.root+size]) # root directory
            read = min(size,(self.sector_size * self.cluster_sects))
            data = data + bytearray(self.data[offset:offset+read])
            size -= read
            if (size < 1):
                return data
            cluster = self.fat[cluster]
        return data

    def _read_dir_chain(self, cluster):
        """Reads an entire directory chain starting at the given cluster (0 for root)."""
        if cluster < 2:
            # root directory is contiguous
            return self.data[self.root:self.root+(self.root_max*32)]
        # directories just occupy as many clusters as in their FAT chain, using a dummy max size
        return self._read_chain(cluster, self.sector_size*self.sectors//self.cluster_sects)

    def _delete_chain(self, cluster):
        """Deletes a FAT chain."""
        while cluster < 0xFF0 and cluster >= 2:
            link = self.fat[cluster]
            self.fat[cluster] = 0
            cluster = link

    def _add_chain(self,data):
        """Adds a block of data to the disk and creates its FAT chain. Returns start cluster, or -1 for failure."""
        cluster_size = self.sector_size * self.cluster_sects
        clusters = (len(data) + cluster_size-1) // cluster_size
        if clusters < 1:
            clusters = 1
        # find a chain of free clusters
        chain = []
        for i in range(2,len(self.fat)):
            # TwoSide Fork
            # replace logical order with side-1-first order
            cside = self.track_sects // self.cluster_sects # clusters belonging to only side-1 on each track (rounds down to avoid split clusters)
            tcount = self.sectors // (self.track_sects * 2) # total track count for each side
            csplit = (tcount-1) * cside # total clusters on side-1 only, first track is useds for boot/FAT/root
            cdual = (self.track_sects * 2) // self.cluster_sects # total clusters per dual-track
            l = i-2
            if l < csplit:
                icluster = l % cside
                itrack = l // cside
                ihead = 0
            else:
                icluster = (l - csplit) % (cdual - cside)
                itrack = (l - csplit) // (cdual - cside)
                ihead = 1
            j = (itrack * cdual) + ((1-ihead) * (cdual-cside)) + icluster + 2
            if j >= self.cluster_limit:
                continue
            if self.fat[j] == 0:
                chain.append(j)
            if len(chain) >= clusters:
                break
        if len(chain) < clusters:
            return -1 # out of space
        # store the FAT chain
        start_cluster = chain[0]
        for i in range(0,len(chain)-1):
            self.fat[chain[i]] = chain[i+1]
        self.fat[chain[len(chain)-1]] = 0xFFF
        # store the data in the given clusters
        data = bytearray(data)
        c = 0
        while len(data) > 0:
            write = min(len(data),cluster_size)
            offset = self._cluster_offset(chain[c])
            self.data[offset:offset+write] = data[0:write]
            c += 1
            data = data[write:]
        # done
        return start_cluster

    def _reserve_side1(self,reserve=False):
        """Counts and optionally reserves free clusters on side 1. Used clusters on side 2 count as -1."""
        # TwoSide Fork       
        count = 0
        for i in range(2,self.cluster_limit):
            cside = self.track_sects // self.cluster_sects
            tcount = self.sectors // (self.track_sects * 2)
            csplit = (tcount-1) * cside
            cdual = (self.track_sects * 2) // self.cluster_sects
            l = i-2
            if l < csplit:
                icluster = l % cside
                itrack = l // cside
                ihead = 0
            else:
                icluster = (l - csplit) % (cdual - cside)
                itrack = (l - csplit) // (cdual - cside)
                ihead = 1
            j = (itrack * cdual) + ((1-ihead) * (cdual-cside)) + icluster + 2
            if l < csplit:
                if self.fat[j] == 0: # unused cluster on side 1
                    if reserve:
                        self.fat[j] = 0xFF0
                    count += 1
            elif self.fat[j] != 0: # used cluster on side 2
                count -= 1
        return count

    def free_side1(self):
        """Counts remaining clusters on side 1. Negative if already full and using side 2."""
        # TwoSide Fork
        return self._reserve_side1(False)

    def close_side1(self):
        """Marks all remaining side 1 clusters as reserved. Prints and returns number of clusters left unused, Negative if side 2 already reached."""
        # TwoSide Fork
        c = self._reserve_side1(True)
        print("Side 1 closed, %d clusters reserved." % c)
        return c
        
    def _files_dir(self, cluster, path):
        """Returns a list of files in the directory starting at the given cluster. Recursive."""
        #print("files_dir(%03X,'%s')" % (cluster, path))
        entries = []
        directory = self._read_dir_chain(cluster)
        for i in range(len(directory) // 32):
            e = self.FileEntry(directory[(i*32):(i*32)+32],cluster,i)
            #print(("entry %d (%08X)\n"%(i,self._dir_entry_offset(cluster,i)))+e.info())
            if e.incipit == 0x00: # end of directory
                return entries
            if e.incipit == Floppy.EMPTY: # empty
                continue
            if (e.attributes & 0x08) != 0: # volume label
                continue
            if (e.attributes & 0x10) != 0: # subdirectory
                if e.path == "." or e.path == "..":
                    continue
                subdir = path + e.path + "\\"
                entries.append(subdir)
                entries = entries + self._files_dir(e.cluster,subdir)
            else:
                entries.append(path + e.path)
        return entries

    def files(self):
        """Returns a list of files in the image."""
        root = self.sector_size * (self.reserved_sects + (self.fat_count * self.fat_sects))
        return self._files_dir(0,"")

    def files_info(self):
        """String of the file list."""
        s = ""
        for path in self.files():
            s += path + "\n"
        return s

    def _dir_entry_offset(self,cluster,dir_index):
        """Find the offset in self.data to a particular directory entry."""
        if (cluster < 2):
            return self.root + (32 * dir_index)
        if (cluster >= 0xFF0):
            raise self.Error("Directory entry %d not in its cluster chain?" % dir_index)
        per_cluster = (self.sector_size*self.cluster_sects)//32
        if (dir_index < per_cluster): # within this cluster
            return self._cluster_offset(cluster) + (32 * dir_index)
        # continue to next cluster
        return self._dir_entry_offset(self.fat[cluster],dir_index-per_cluster)

    def delete_file(self, entry):
        """Deletes a FileEntry."""
        self._delete_chain(entry.cluster) # delete its FAT chain
        offset = self._dir_entry_offset(entry.dir_cluster,entry.dir_index)
        self.data[offset+0] = Floppy.EMPTY # empty this entry

    def _find_path_dir(self, cluster, path):
        """Recursive find path, breaking out subdirectories progressively."""
        #print("_find_path_dir(%03X,'%s')" % (cluster,path))
        separator = path.find("\\")
        path_seek = path
        path_next = ""
        if separator >= 0:
            path_seek = path[0:separator]
            path_next = path[separator+1:]
        directory = self._read_dir_chain(cluster)
        for i in range(len(directory) // 32):
            e = self.FileEntry(directory[(i*32):(i*32)+32],cluster,i)
            if e.incipit == 0x00: # end of directory
                return None
            if e.incipit == Floppy.EMPTY: # empty
                continue
            if (e.attributes & 0x08) != 0: # volume label
                continue
            if (e.attributes & 0x10) != 0: # subdirectory
                if e.path == "." or e.path == "..":
                    continue
                if e.path == path_seek:
                    if (len(path_next) > 0):
                        return self._find_path_dir(e.cluster, path_next)
                    else:
                        return e
            elif e.path == path_seek and path_next == "":
                return e
        return None

    def find_path(self, path):
        """Finds a FileEntry for a given path."""
        return self._find_path_dir(0,path)

    def _delete_tree(self,de):
        """Recursively deletes directory entries."""
        #print("_delete_tree\n" + de.info())
        directory = self._read_dir_chain(de.cluster)
        for i in range(len(directory) // 32):
            e = self.FileEntry(directory[(i*32):(i*32)+32],de.cluster,i)
            #print(e.info())
            if e.incipit == 0x00: # end of directory
                return
            if e.incipit == Floppy.EMPTY: # empty
                continue
            if (e.attributes & 0x08) != 0: # volume label
                continue
            if (e.attributes & 0x10) != 0: # subdirectory
                if e.path == "." or e.path == "..":
                    continue
                self._delete_tree(e) # recurse
                self.delete_file(e)
            else:
                self.delete_file(e)

    def delete_path(self, path):
        """Finds a file or directory and deletes it (recursive), if it exists. Returns True if successful."""
        e = self.find_path(path)
        if (e == None):
            return False
        if (e.attributes & 0x10) != 0:
            self._delete_tree(e)
        self.delete_file(e)
        return True

    def _add_entry(self, dir_cluster, entry):
        """
        Adds an entry to a directory starting at the given cluster, appending a new cluster if needed.
        Sets entry.dir_cluster and entry.dir_index to match their new directory.
        Returns False if out of space.
        """
        #print(("_add_entry(%d):\n"%dir_cluster) + entry.info())
        directory = self._read_dir_chain(dir_cluster)
        dir_len = len(directory)//32
        i = 0
        terminal = False
        while i < dir_len:
            e = self.FileEntry(directory[(i*32):(i*32)+32],dir_cluster,i)
            #print(e.info())
            if e.incipit == 0x00:
                terminal = True # make sure to add another terminal entry after this one
                break
            if e.incipit == Floppy.EMPTY:
                break
            i += 1
        # extend directory if out of room
        if i >= dir_len:
            if dir_cluster < 2:
                return False # no room in root
            # add a zero-filled page to the end of this directory's FAT chain
            chain = self._add_chain(bytearray([0]*(self.sector_size*self.cluster_sects)))
            if (chain < 0):
                return False # no free clusters
            tail = dir_cluster
            while self.fat[tail] < 0xFF0:
                tail = self.fat[tail]
            self.fat[tail] = chain
            self.fat[chain] = 0xFFF
        # insert entry
        entry.dir_cluster = dir_cluster
        entry.dir_index = i
        offset = self._dir_entry_offset(dir_cluster,i)
        self.data[offset:offset+32] = entry.compile()
        # add a new terminal if needed
        if terminal:
            i += 1
            if i < dir_len: # if it was the last entry, no new terminal is needed
                offset = self._dir_entry_offset(dir_cluster,i)
                self.data[offset:offset+32] = Floppy.FileEntry.new_terminal().compile()
                
        # success!
        return True

    def _add_dir_recursive(self, cluster, path):
        """Recursively creates directory, returns cluster of created dir, -1 if failed."""
        #print("_add_dir_recursive(%03X,'%s')"%(cluster,path))
        separator = path.find("\\")
        path_seek = path
        path_next = ""
        if separator >= 0:
            path_seek = path[0:separator]
            path_next = path[separator+1:]
        directory = self._read_dir_chain(cluster)
        for i in range(len(directory) // 32):
            e = self.FileEntry(directory[(i*32):(i*32)+32],cluster,i)
            #print(e.info())
            if e.incipit == 0x00: # end of directory
                break
            if e.incipit == Floppy.EMPTY: # empty
                continue
            if (e.attributes & 0x10) != 0: # subdirectory
                if e.path == path_seek: # already exists
                    if len(path_next) < 1:
                        return e.cluster # return existing directory
                    else:
                        return self._add_dir_recursive(e.cluster,path_next) # keep descending
        # not found: create the directory
        dp0 = Floppy.FileEntry.new_dir("_") # .
        dp1 = Floppy.FileEntry.new_dir("__") # ..
        dp1.cluster = cluster
        dir_block = dp0.compile() + dp1.compile() + bytearray([0] * ((self.sector_size*self.cluster_sects)-64))
        new_cluster = self._add_chain(dir_block)
        if new_cluster < 0:
            return -1 # out of space
        # fix up "." to point to itself
        dp0.cluster = new_cluster
        offset = self._dir_entry_offset(new_cluster,0)
        self.data[offset:offset+32] = dp0.compile()
        # fix special directory names (FileEntry.compile() is incapable of . or ..)
        self.data[offset+ 0:offset+11] = bytearray(".          ".encode("ASCII"))
        self.data[offset+32:offset+43] = bytearray("..         ".encode("ASCII"))
        # create entry to point to new directory cluster
        new_dir = Floppy.FileEntry.new_dir(path_seek)
        new_dir.cluster = new_cluster
        if not self._add_entry(cluster, new_dir):
            self._delete_chain(new_cluster)
            return -1 # out of space
        # return the entry if tail is reached, or keep descending
        if len(path_next) < 1:
            return new_cluster
        else:
            return self._add_dir_recursive(new_cluster,path_next)

    def add_dir_path(self, path):
        """
        Recursively ensures that the given directory path exists, creating it if necessary.
        Path should not end in backslash.
        Returns cluster of directory at path, or -1 if failed.
        """
        if (len(path) < 1):
            return 0 # root
        return self._add_dir_recursive(0,path)

    def add_file_path(self, path, data):
        """
        Adds the given data as a file at the given path.
        Will automatically create directories to complete the path.
        Returns False if failed.
        """
        self.delete_path(path) # remove file if it already exists
        dir_path = ""
        file_path = path
        separator = path.rfind("\\")
        if (separator >= 0):
            dir_path = path[0:separator]
            file_path = path[separator+1:]
        dir_cluster = self.add_dir_path(dir_path)
        if dir_cluster < 0:
            return False # couldn't find or create directory
        cluster = self._add_chain(data)
        if (cluster < 0):
            return False # out of space
        entry = Floppy.FileEntry.new_file(file_path)
        entry.cluster = cluster
        entry.size = len(data)
        if not self._add_entry(dir_cluster, entry):
            self._delete_chain(cluster)
            return False # out of space for directory entry
        offset = self._dir_entry_offset(entry.dir_cluster, entry.dir_index)
        self.data[offset:offset+32] = entry.compile()
        return True

    def extract_file_path(self, path):
        """Finds a file and returns all of its data. None on failure."""
        e = self.find_path(path)
        if e == None:
            return None
        return self._read_chain(e.cluster, e.size)
        
    def set_volume_id(self, value=None):
        """Sets the volume ID. None for time-based."""
        if (value == None):
            (date,time) = Floppy.FileEntry.fat_time_now()
            value = time | (date << 16)
        self.volume_id = value & 0xFFFFFFFF

    def set_volume_label(self, label):
        """Sets the volume label. Creates one if necessary."""
        self.data[38] = 0x29
        self.volume_label = label
        self.data[54:62] = Floppy._filestring("FAT12",8)
        # adjust existing volume entry in root
        directory = self._read_dir_chain(0)
        for i in range(len(directory) // 32):
            e = self.FileEntry(directory[(i*32):(i*32)+32],0,i)
            if e.incipit == 0x00: # end of directory
                break
            if e.incipit == Floppy.EMPTY: # empty
                continue
            if (e.attributes & 0x08) != 0: # existing volume label
                offset = self._dir_entry_offset(0,i)
                self.data[offset:offset+11] = Floppy._filestring(label,11)
                return
        # volume entry does not exist in root, add one
        self._add_entry(0,Floppy.FileEntry.new_volume(label))
        return

    def open(filename):
        """Opens a floppy image file and creates a Floppy() instance from it."""
        return Floppy(open(filename,"rb").read())

    def flush(self):
        """Commits all unfinished changes to self.data image."""
        self._fat_flush()
        self._boot_flush()

    def save(self, filename):
        """Saves image (self.data) to file. Implies flush()."""
        self.flush()
        open(filename,"wb").write(self.data)

    def extract_all(self, out_directory):
        """Extracts all files from image to specified directory."""
        for in_path in self.files():
            out_path = os.path.join(out_directory,in_path)
            out_dir = os.path.dirname(out_path)
            if not os.path.exists(out_dir):
                try:
                    os.makedirs(out_dir)
                except OSError as e:
                    if e.errono != errno.EEXIST:
                        raise
            if not in_path.endswith("\\"):
                open(out_path,"wb").write(self.extract_file_path(in_path))
                print(out_path)
            else:
                print(out_path)

    def add_all(self, in_directory, prefix=""):
        """
        Adds all files from specified directory to image.
        Files will be uppercased. Long filenames are not checked and will cause an exception.
        prefix can be used to prefix a directory path (ending with \) to the added files.
        """
        result = True
        def dospath(s):
            s = s.upper()
            s = s.replace("/","\\")
            return s
        if len(in_directory) < 1:
            in_directory = "."
        in_directory = os.path.normpath(in_directory) + os.sep
        for (root, dirs, files) in os.walk(in_directory):
            base = root[len(in_directory):]
            for d in dirs:
                dir_path = prefix + dospath(os.path.join(base,d))
                result = result and (self.add_dir_path(dir_path) >= 0)
                print(dir_path + "\\")
            for f in files:
                file_path = prefix + dospath(os.path.join(base,f))
                data = open(os.path.join(root,f),"rb").read()
                result = result and self.add_file_path(file_path,data)
                print(file_path + " (%d bytes)" % len(data))
        return result
s
