#!/usr/bin/env python3
#
# makenib.py
# Version 1
# Brad Smith, 2021
# http://rainwarrior.ca
#
# Simple file operations for an Apple II NIB disk image.
# Public domain.

#
# Able to parse a NIB file and read Apple DOS 3.2 and 3.3 formatted data.
# Can list the file catalog and extract individual files.
#
# Example:
#     n = Nibby.open("disk.nib")
#     print(n.info()) # print disk information and file catalog
#     # extract all files from disk:
#     for f in n.catalog().file:
#     (d,v) = n.extract(f)
#     if v:
#         open(f.name,"wb").write(d)
#         print(f.name + " extracted")
#     else:
#         print(f.name + " invalid")
#

import sys
assert sys.version_info[0] == 3, "Python 3 required."

def dump(d,offset=0,columns=32):
    """Hexadecimal dump of data with given address."""
    s = ""
    for i in range(len(d)):
        if (i % columns) == 0:
            s += "$%06X:" % (offset+i)
        s += " %02X" % d[i]
        if (i % columns) == (columns - 1) and i != (len(d)-1):
            s += "\n"
    return s

def printable(d,default='.'):
    """Convert a byte array into printable ASCII. Default if not printable."""
    s = bytearray([ord(default)] * len(d))
    for i in range(len(d)):
        c = d[i] & 0x7F
        if c >= 0x20 and c < 0x7F:
            s[i] = c
    return s.decode("ASCII")

def dump_printable(d,offset=0,columns=32):
    """Printable dump of data with given address."""
    if len(d) == 0:
        return "$%06X []\n" % offset
    s = ""
    for i in range(0,len(d),columns):
        s += "$%06X [" % (offset+i)
        s += printable(d[i:i+columns])
        s += "]\n"
    return s

class Nibby:
    """
    .tracks - Tracks in disk image.
    .data - Bytearray of the disk image.
    .td - Bytearray of each track.
    open - open a NIB file
    read - read a sector of data
    catalog - read the DOS file catalog
    extract - extract a file
    info - display information and catalog
    dump_track - display tracks in raw hex
    """

    TLEN = 0x1A00 # bytes per track in NIB file
    
    class File:
        """
        Apple DOS catalog file entry.
        .deleted - If the file was deleted.
        .track/.sector - Address of sector list.
        .locked - If the file is read-only.
        .type - Type byte. (Can reference TYPE_NAME.)
        .name - Printable 30 character filename.
        .size - Size of file (256 byte sector count).
        """
        
        TYPE_NAME = {
            0x00 : "TEXT",
            0x01 : "INTEGER BASIC",
            0x02 : "APPLESOFT BASIC",
            0x04 : "BINARY",
            0x08 : "S TYPE",
            0x10 : "OBJECT MODULE",
            0x20 : "A TYPE",
            0x40 : "B TYPE" }
        
        def __init__(self,fd):
            self.data = fd
            self.deleted = False
            self.track = fd[0x00]
            self.sector = fd[0x01]
            self.locked = (fd[0x02] & 0x80) != 0
            self.type = fd[0x02] & 0x7F
            self.name = printable(fd[0x03:0x21])
            self.size = fd[0x21] + (fd[0x22] << 8)
            if self.track == 0xFF: # deleted file
                self.deleted = True
                self.track = fd[0x20] # track relocated to end of name
        
        def extract(self,nibby,dos=None,fill=0xAA):
            data = bytearray()
            valid = True
            slt = self.track
            sls = self.sector
            while (slt != 0):
                # read sector list
                (sld, v) = nibby.read(slt,sls,dos)
                if not v:
                    valid = False
                    break
                slt = sld[0x01] # pointer to next sector list (0 if done)
                sls = sld[0x02]
                for si in range(0x0C,0x100,2):
                    st = sld[si+0]
                    ss = sld[si+1]
                    #print("%02d:%02d" % (st,ss))
                    if st == 0:
                        break
                    (sd, v) = nibby.read(st,ss,dos)
                    if not v:
                        valid = False
                        data += bytearray([fill]*256)
                    else:
                        data += sd
            return (data, valid)

        def info(self):
            s = ""
            if self.type in Nibby.File.TYPE_NAME:
                s = " " + Nibby.File.TYPE_NAME[self.type]
            if self.deleted:
                s += " (DELETED)"
            return "[%s] %02d:%02d %s %6db %02X%s" % (
                self.name,
                self.track, self.sector,
                "RO" if self.locked else "RW",
                self.size * 256,
                self.data[0x02],s)

    class Catalog:
        """
        .ver - Table of contents (DOS) version
        .vol - Table of contents Volume byte
        .file - List of File entries
        .valid - Whether the catalog was read
        """
        def info(self):
            s = "Version: %d\n" % (self.ver)
            s += "Volume: %02X\n" % (self.vol)
            for f in self.file:
                s += f.info() + "\n"
            return s

    class Sector:
        """
        .track - physical track index
        .dos
            - 0 invalid (other fields are also invalid/unassigned)
            - 1 not used
            - 2 DOS 3.2 sector-13
            - 3 DOS 3.3 sector-16
        .vol - volume
        .trk - reported track
        .sct - sector
        .sum - checksum
        .valid - true if checksum matches
        .data - offset to data, if found
        """

        FORMAT_NAME = [ "Invalid", "????? 1", "DOS 3.2", "DOS 3.3" ]
        FORMAT_SIZE = [ 0, 0, 410, 342 ]

        NIBBLE_5AND3 = [
            0xAB, 0xAD, 0xAE, 0xAF, 0xB5, 0xB6, 0xB7, 0xBA,
            0xBB, 0xBD, 0xBE, 0xBF, 0xD6, 0xD7, 0xDA, 0xDB,
            0xDD, 0xDE, 0xDF, 0xEA, 0xEB, 0xED, 0xEE, 0xEF,
            0xF5, 0xF6, 0xF7, 0xFA, 0xFB, 0xFD, 0xFE, 0xFF ]
        NIBBLE_6AND2 = [
            0x96, 0x97, 0x9A, 0x9B, 0x9D, 0x9E, 0x9F, 0xA6,
            0xA7, 0xAB, 0xAC, 0xAD, 0xAE, 0xAF, 0xB2, 0xB3,
            0xB4, 0xB5, 0xB6, 0xB7, 0xB9, 0xBA, 0xBB, 0xBC,
            0xBD, 0xBE, 0xBF, 0xCB, 0xCD, 0xCE, 0xCF, 0xD3,
            0xD6, 0xD7, 0xD9, 0xDA, 0xDB, 0xDC, 0xDD, 0xDE,
            0xDF, 0xE5, 0xE6, 0xE7, 0xE9, 0xEA, 0xEB, 0xEC,
            0xED, 0xEE, 0xEF, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6,
            0xF7, 0xF9, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE, 0xFF ]
        
        DENIBBLE_5AND3 = {k:v for v,k in enumerate(NIBBLE_5AND3)}
        DENIBBLE_6AND2 = {k:v for v,k in enumerate(NIBBLE_6AND2)}
        
        def __init__(self,td,o,track):
            """
            td = track data, o = offset, track = physical track index
            """
            self.track = track
            self.valid = False
            self.data = None
            self.dos = 0
            if   td[(o+0) % Nibby.TLEN] != 0xD5:
                return
            if   td[(o+1) % Nibby.TLEN] != 0xAA:
                return
            if   td[(o+2) % Nibby.TLEN] == 0xB5: # DOS 3.2 sector D5 AA B5
                self.dos = 2
            elif td[(o+2) % Nibby.TLEN] == 0x96: # DOS 3.3 sector D5 AA 96
                self.dos = 3
            else:
                return # unknown
            self.vol = ((td[(o+3)%Nibby.TLEN] << 1)|1) & td[(o+ 4)%Nibby.TLEN]
            self.trk = ((td[(o+5)%Nibby.TLEN] << 1)|1) & td[(o+ 6)%Nibby.TLEN]
            self.sct = ((td[(o+7)%Nibby.TLEN] << 1)|1) & td[(o+ 8)%Nibby.TLEN]
            self.sum = ((td[(o+9)%Nibby.TLEN] << 1)|1) & td[(o+10)%Nibby.TLEN]
            self.valid = ((self.vol ^ self.trk ^ self.sct) == self.sum)
            dataseek = 0
            DATAPROLOGUE = [0xD5,0xAA,0xAD]
            for dataseek in range(256):
                match = True
                for i in range(len(DATAPROLOGUE)):
                    if td[(o+dataseek+i) % Nibby.TLEN] != DATAPROLOGUE[i]:
                        match = False
                        break
                if match:
                    self.data = (o+dataseek) % Nibby.TLEN
                    break

        def read(self,td):
            """Decode sector data from track data. Returns (data,checksum test)"""
            if self.data == None:
                return (None,False)
            nib = bytearray(Nibby.Sector.FORMAT_SIZE[self.dos] + 1)
            for i in range(len(nib)):
                nib[i] = td[(self.data + i + 3) % Nibby.TLEN]
            #print(("NIB %02d:%02d\n" % (self.track,self.sct)) + dump(nib) + "\n")
            checksum = 0
            data = [0] * 256
            if (self.dos == 2):
                for i in range(len(nib)):
                    b = nib[i]
                    if b in Nibby.Sector.DENIBBLE_5AND3:
                        nib[i] = Nibby.Sector.DENIBBLE_5AND3[b]
                    checksum ^= nib[i]
                    nib[i] = checksum
                #print("DENIB:\n" + dump(nib,columns=51) + "\n")
                for i in range(51):
                    j = 50 - i
                    di = i * 5
                    nib3a = nib[153-((0*51)+j)]
                    nib3b = nib[153-((1*51)+j)]
                    nib3c = nib[153-((2*51)+j)]
                    data[di+0] = (nib[154+(0*51)+j] << 3) | ((nib3a >> 2) & 0x7)
                    data[di+1] = (nib[154+(1*51)+j] << 3) | ((nib3b >> 2) & 0x7)
                    data[di+2] = (nib[154+(2*51)+j] << 3) | ((nib3c >> 2) & 0x7)
                    data[di+3] =  nib[154+(3*51)+j]
                    data[di+4] =  nib[154+(4*51)+j]
                    data[di+3] = (data[di+3] << 1) | ((nib3a >> 1) & 1)
                    data[di+3] = (data[di+3] << 1) | ((nib3b >> 1) & 1)
                    data[di+3] = (data[di+3] << 1) | ((nib3c >> 1) & 1)
                    data[di+4] = (data[di+4] << 1) | ((nib3a >> 0) & 1)
                    data[di+4] = (data[di+4] << 1) | ((nib3b >> 0) & 1)
                    data[di+4] = (data[di+4] << 1) | ((nib3c >> 0) & 1)
                data[255] = (nib[154+255] << 3) | (nib[153-153] & 0x7)
            elif (self.dos == 3):
                for i in range(len(nib)):
                    b = nib[i]
                    if b in Nibby.Sector.DENIBBLE_6AND2:
                        nib[i] = Nibby.Sector.DENIBBLE_6AND2[b]
                    checksum ^= nib[i]
                    nib[i] = checksum
                #print("DENIB:\n" + dump(nib) + "\n")
                for i in range(256):
                    data[i] = nib[86 + i] # high 6 bits
                    # low 2 bits
                    ti = i % 86
                    data[i] = (data[i] << 1) | (nib[ti] & 1)
                    nib[ti] >>= 1
                    data[i] = (data[i] << 1) | (nib[ti] & 1)
                    nib[ti] >>= 1
            else:
                return (None,False)
            for i in range(len(data)):
                data[i] &= 0xFF
            return (bytearray(data),checksum==0)
        
        def info(self):
            if self.dos == 0:
                return "Invalid"
            s = "T%02d=%02d:%02d %s Vol %02X" % (self.track,self.trk,self.sct,Nibby.Sector.FORMAT_NAME[self.dos],self.vol)
            if not self.valid:
                s += " checksum fail"
            return s

    def read(self,track,sector,dos=None):
        """Finds matching sector and returns (data,checksum test)."""
        for s in self.sector:
            if s.track != track or s.sct != sector:
                continue
            if dos != None and s.dos != dos:
                continue
            return s.read(self.td[track])
        return (None,False)

    def parse(self):
        self.tracks = len(self.data) // Nibby.TLEN
        self.td = []
        self.sector = []
        self.sector_count = [0,0,0,0]
        for t in range(self.tracks):
            self.td.append(self.data[t*Nibby.TLEN:(t+1)*Nibby.TLEN])
            # find segments
            so = 0
            for so in range(Nibby.TLEN):
                sector = Nibby.Sector(self.td[t],so,t)
                if sector.dos > 0:
                    self.sector.append(sector)
                    #print(sector.info())
                    #(sd,sv) = sector.read(self.td[t])
                    #if sv:
                    #    print(dump(sd))
                    #    pass
                    #else:
                    #    print("Invalid!")
                    #    pass
                    self.sector_count[sector.dos] += 1

    def catalog(self,track=17,sector=0,dos=None):
        """Looks for a catalog of files."""
        (cd,valid) = self.read(track,sector,dos)
        cat = Nibby.Catalog()
        cat.ver = 0
        cat.vol = 0
        cat.file = []
        cat.valid = False
        if not valid:
            return cat
        cat.valid = True
        cat.ver = cd[0x03] # DOS version
        cat.vol = cd[0x06] # disk volume
        track = cd[0x01]
        sector = cd[0x02]
        while track > 0 or sector > 0:
            (cd,valid) = self.read(track,sector,dos)
            if not valid:
                break
            track = cd[0x01]
            sector = cd[0x02]
            for i in range(7):
                fo = 0x0B + (35 * i)
                fd = cd[fo:fo+35]
                if fd[0x00] != 0:
                    f = Nibby.File(fd)
                    cat.file.append(f)
        return cat

    def extract(self,file):
        """Extracts a catalog file entry as: (data,valid)"""
        return file.extract(self)

    def __init__(self,data=None,filename="NO FILENAME"):
        self.filename = filename
        self.data = bytearray(data)
        self.parse()

    def open(filename):
        """Opens a NIB image file and creates a Nibby() instance from it."""
        return Nibby(open(filename,"rb").read(),filename)

    def dump_track(self,t=None):
        """HEX dump of track data, or all tracks if unspecified."""
        if t != None:
            return dump(self.td[t])
        else:
            s = ""
            for i in range(self.tracks):
                s += ("T%02d:\n" % i) + self.dump_track(i,None,text) + "\n"
            return s

    def info(self):
        """String of information about the disk image."""
        extrabytes = len(self.data) % Nibby.TLEN
        s = self.filename + "\n"
        s += "Tracks: %d\n" % self.tracks
        if extrabytes > 0:
            s += "Extra bytes: %d\n" % (extrabytes)
        #print(self.dump_track())
        s += "Sectors:\n"
        for d in range(0 ,4):
            if self.sector_count[d] < 1:
                continue
            t = -1
            tc = 0
            for sector in self.sector:
                if sector.dos == d:
                    if t != sector.track:
                        if tc > 0:
                            s += "\n"
                        tc = 0
                        t = sector.track
                        s += "%s T%02d:" % (Nibby.Sector.FORMAT_NAME[d],t)
                    s += " %02d" % (sector.sct)
                    tc += 1
            if tc > 0:
                s += "\n"
        cat = self.catalog()
        if not cat.valid:
            s += "No catalog.\n"
        else:
            s += "Catalog:\n" + cat.info()
        return s
