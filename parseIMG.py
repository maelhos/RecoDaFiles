import io
import os
import time
from struct import unpack, pack
from zlib import crc32
from enum import Enum

import Partitions.ParseNprint as ParseNprint
import Partitions.NTFSpart as NTFSpart
import Partitions.UKpart as UKpart

# All strings that should be user input
#filename = "image.img"
filename = "\\\\.\\PhysicalDrive2"

# All constants
LBA_SIZE = 512
GPTs_LBA = 1
DEV = True

MAX_SAVE_SIZE =  -1 # -1 for no save max size and size in bytes
MAX_SAVE_SIZE = 3*2**30 # 3 Gb

START_ADDR = int(2.38+1+0.136)*2**30
RECOVERY_MODE = 4
# 0 : recover every file
# 1 : recover ntfs deleted files
# 2 : recover ntfs deleted files + carve for files in unparsed region
# 3 : only carve for files in free region
# 4 : carve for files everywhere

class PartitionType(Enum):  # supported ones
	UNKNOWN = 0
	NTFS = "NTFS"
	EXT4 = "Ext4"
	FAT32 = "Fat32"

class Image:		
	def __init__(self,img=None):
		self.parsed = False
		self.loaded = False
		self.lba_size = LBA_SIZE
		self.loadException = Exception("load take an open() element as parameter")
		
		if img != None:
			self.loaded = True
			if type(img) == int:
				self.img = img
			else:
				raise Exception("load take an fd element as parameter")
	
	def load(self,img):
		self.loaded = True
		if isinstance(img,io.IOBase):
			self.img = img
		else:
			raise Exception("load take an open() element as parameter")
	
	def getSize(self):
		self.checkLoaded()
		self.size = 2794*2**30
		#self.size = os.stat(filename).st_size
		#print(self.size)
		return self.size

	def checkLoaded(self):
			if not self.loaded:
				raise self.loadException
				return False
			return True	

	def readBytes(self,nthLBA,offset,size):
		return self.nthLBA(nthLBA)[offset:offset+size]

	def nthLBA(self,n):
		self.checkLoaded()
		return self.readB(n*self.lba_size,self.lba_size)

	def readB(self,addr,s):
		self.checkLoaded()
		os.lseek(self.img,addr,os.SEEK_SET)
		return os.read(self.img,s)

	def recover(self):
		self.uniqueRecoID = "reco_" + str(hex(int(time.time()*10**3))[2:])
		while os.path.isdir(self.uniqueRecoID):
			self.uniqueRecoID = "reco_" + str(hex(int(time.time()*10**3))[2:])

		os.mkdir(self.uniqueRecoID)
		os.mkdir(self.uniqueRecoID+"/carved")
		os.mkdir(self.uniqueRecoID+"/ntfsAll")
		os.mkdir(self.uniqueRecoID+"/ntfsDeleted")

		print("Saving Recovery to " + self.uniqueRecoID)

		self.getSize()
		if RECOVERY_MODE == 0: # done
			self.searchRegion = [(0,self.size)] # will be set after parse  [(addr,offset/search_size) , ...]
			self.parse()
			self.recoverNTFSnotdeleted()
			self.recoverNTFSdeleted()

			self.shrinkSearchRegion()
			self.carve()
		elif RECOVERY_MODE == 1: # done
			self.searchRegion = [(0,self.size)] # will remain (0,0) because only NTFS deleted files
			self.parse()
			self.recoverNTFSdeleted()
		elif RECOVERY_MODE == 2: # done
			self.searchRegion = [(0,self.size)] # will be set after parse
			self.parse()
			self.recoverNTFSdeleted()

			self.shrinkSearchRegion()
			self.carve()
		elif RECOVERY_MODE == 3: # done
			self.searchRegion = [(0,self.size)]# will be set after parse
			self.parse()

			self.shrinkSearchRegion()
			self.carve()
		elif RECOVERY_MODE == 4: # done
			self.searchRegion = [(0,self.size)]
			self.carve()
			# dont need to parse

		print(self.getSaveFolderSize(), "Bytes were used for saving")
	def getSaveFolderSize(self):
		total_size = 0
		for dirpath, dirnames, filenames in os.walk(self.uniqueRecoID):
			for f in filenames:
				fp = os.path.join(dirpath, f)
				# skip if it is symbolic link
				if not os.path.islink(fp):
					total_size += os.path.getsize(fp)
	
		return total_size

	def shrinkSearchRegion(self):
		for ntPart in self.ntfsParts:
			for f in ntPart.files:
				if f.data != [(0,0)]:
					for d in f.data:
						_sa = d[0]
						_ea = d[0] + d[1]
						_sr = []
						for f in self.searchRegion:
							if _sa > f[0] and _ea <= f[1]:
								_sr.append((f[0] , _sa ))
								_sr.append((_ea , f[1] ))
							else:
								_sr.append(f)
						self.searchRegion = _sr

	def checkFileSaveNotExeded(self):
		if MAX_SAVE_SIZE == -1:
			return
		else:
			if self.getSaveFolderSize()	>= MAX_SAVE_SIZE:
				print("SAVE SIZE EXEDED OR FULL !! EXITING")
				quit()

	def recoverNTFSdeleted(self):
		for ntPart in self.ntfsParts:
			for f in ntPart.files:
				if f.deleted == True:
					_t = open(self.uniqueRecoID+"/ntfsDeleted/{}".format(f.fileName),"wb+")
					_t.write(f.getData())
					_t.close()
					self.checkFileSaveNotExeded()

	def recoverNTFSnotdeleted(self):
		for ntPart in self.ntfsParts:
			for f in ntPart.files:
				if f.deleted == False:
					_t = open(self.uniqueRecoID+"/ntfsAll/{}".format(f.fileName),"wb+")
					_t.write(f.getData())
					_t.close()
					self.checkFileSaveNotExeded()

	def carve(self):
		#print(self.searchRegion)
		for ft in ParseNprint.filetypes:
			print("Searching for {} files ...".format(ft["type"])) 
			for sp in self.searchRegion:
				self.searchforfile(sp[0]+START_ADDR,sp[1],ft["beg"],ft["end"],ft["ext"],ParseNprint.filetypes.index(ft))

	def parse(self):
		self.checkLoaded()
		self.parsed = True
		self.getSize()
		
		# ONLY GPT IS SUPPORTED
		self.htype = self.readBytes(GPTs_LBA,0x0,0x8)


		print("Parsing Partiton before recovery ...\n")
		if self.htype == b"EFI PART":
			self.parseGPT()
		else:

			print("Partition table unrecognized...")
			print("setting Default values")
			self.firstUsableLBA = 0
			self.lastUsableLBA = self.size//self.lba_size

		
				
	def searchforfile(self,startaddr,maxx,begin,end,ext,ftIndex,chunksize=512):
		
		if (maxx+startaddr) % chunksize != 0:
			maxx += chunksize - ((maxx+startaddr) % chunksize)
		assert (maxx+startaddr) % chunksize == 0
		addr = startaddr
		_tempfile = b""
		isinfile = False	

		while addr < maxx:
			_chunk = self.readB(addr,chunksize)
			if begin in _chunk and not isinfile:
				isinfile = True
				_tempfile += _chunk[_chunk.index(begin):]
			elif end in _chunk and isinfile:
				isinfile = False
				_chunk = _chunk[::-1]
				_chunk = _chunk[_chunk.index(end[::-1]):]
				_tempfile += _chunk[::-1]

				_t = open(self.uniqueRecoID + "/carved/file{}.{}".format(ParseNprint.filetypes[ftIndex]["count_temp_file"],ext),"wb+")
				ParseNprint.filetypes[ftIndex]["count_temp_file"] += 1
				_t.write(_tempfile)
				_t.close()
				self.checkFileSaveNotExeded()

				_tempfile = b""
			elif isinfile :
				_tempfile += _chunk
			addr += chunksize

	def parseGPT(self):

		self.checkLoaded()

		assert self.readBytes(GPTs_LBA,0x0,0x8) == b"EFI PART"

		self.version = str(float(unpack(">I",self.readBytes(GPTs_LBA,0x8,0x4))[0] >> 8 + unpack(">B",self.readBytes(GPTs_LBA,0x8 + 3,0x1))[0]))

		self.headerSize = unpack("<I",self.readBytes(GPTs_LBA,0xc,0x4))[0]

		self.crc32 = unpack("<I",self.readBytes(GPTs_LBA,0x10,0x4))[0]
		## check
		_header = list(self.readBytes(GPTs_LBA,0x0,self.headerSize))
		_header[0x10] = 0
		_header[0x11] = 0
		_header[0x12] = 0
		_header[0x13] = 0
		_header = bytearray(_header)

		_crc32 = crc32(_header)

		if self.crc32 == _crc32:
			_checkCRC32 = "CRC32 valid and checked"
		else:
			_checkCRC32 = "CRC32 not valid ..."

		assert self.readBytes(GPTs_LBA,0x14,0x4) == b"\x00\x00\x00\x00"
		self.pCurrentLBA = unpack("<Q",self.readBytes(GPTs_LBA,0x18,0x8))[0]
		self.pBackupLBA = unpack("<Q",self.readBytes(GPTs_LBA,0x20,0x8))[0]


		self.firstUsableLBA = unpack("<Q",self.readBytes(GPTs_LBA,0x28,0x8))[0]
		self.lastUsableLBA = unpack("<Q",self.readBytes(GPTs_LBA,0x30,0x8))[0]
		self.nLBA = self.size//512

		self.DiskGUID = ParseNprint.ComputeGUID(self.readBytes(GPTs_LBA,0x38,0x10))

		self.startLBA = unpack("<Q",self.readBytes(GPTs_LBA,0x48,0x8))[0]

		self.maxPartNum = unpack("<I",self.readBytes(GPTs_LBA,0x50,0x4))[0]
		self.partEntrySize = unpack("<I",self.readBytes(GPTs_LBA,0x54,0x4))[0]

		## list partitions entries

		_addr = self.lba_size*(GPTs_LBA + 1)
		self.numPart = 0x00

		while self.readB(_addr ,0x10) != b"\x00"*0x10:
			self.numPart += 1
			_addr += self.partEntrySize

		# PARSE THEM
		self.parts = []

		_addr = self.lba_size*(GPTs_LBA + 1)
		for i in range(self.numPart):
			_tClass = PartitionEntry(self,self.readB(_addr ,0x80))
			_tClass.parse()
			self.parts.append(_tClass)
			_addr += self.partEntrySize
		
		self.ukParts = []
		self.ntfsParts = []
		self.ext4Parts = []
		self.fat32Parts = []
		
		for i in range(len(self.parts)):
			if self.parts[i].type == PartitionType.NTFS:
				self.parts[i].SpecialPartID = len(self.ntfsParts)
				_tClass = NTFSpart.ntfsPart(self,self.parts[i].firstLBA,self.parts[i].lastLBA,i)
				_tClass.parse()
				self.ntfsParts.append(_tClass)
			elif self.parts[i].type == PartitionType.UNKNOWN:
				self.parts[i].SpecialPartID = len(self.ukParts)
				_tClass = UKpart.ukPart(self,self.parts[i].firstLBA,self.parts[i].lastLBA,i)
				_tClass.parse()
				self.ukParts.append(_tClass)
			else:
				print("Should not append ...")
		
		print(" Parsing : GPT - Table")
		print("Size : {} Bytes or {} Gb".format(ParseNprint.groupby3(self.size),round(self.size/10**9,2)))
		print("Version : " + self.version)
		if DEV:
			print("Header Size : {} bytes".format(self.headerSize))

			print()

			print("CRC32 {} : {}".format(hex(self.crc32)[2:],_checkCRC32))

			print()
			
			print("LBA(1) pointer : {}".format(self.pCurrentLBA))
			print("LBA(backup) pointer : {}".format(self.pBackupLBA))

			print()
			
			print("First usable LBA : {} / {}".format(self.firstUsableLBA,self.nLBA))
			print("Last usable LBA : {} / {}".format(self.lastUsableLBA,self.nLBA))
		print("Disk GUID : {}".format(self.DiskGUID))
		if DEV:
			print()
			
			print("Starting LBA of array of partition entries : LBA_{}".format(self.startLBA))
		print("{} Partitions found out of {} possibles with header of sizes {} Bytes".format(self.numPart,self.maxPartNum,self.partEntrySize))

		print()

		for i in range(len(self.parts)):
			print("Looking at " + ParseNprint.engnumsufix(i+1) + " partition : ")
			print("\t-> Partition Name : " + self.parts[i].name)
			if self.parts[i].partTypeGUID in ParseNprint.guids:
				print("\t-> Operating System : " + ParseNprint.op[ParseNprint.guids[self.parts[i].partTypeGUID][0]])
				print("\t-> Partition type : " + ParseNprint.guids[self.parts[i].partTypeGUID][1])
			else: 
				print("\t-> Partition type and operation system unrecognized ...")
			if DEV:
				print("\t-> Partition Type GUID : " + self.parts[i].partTypeGUID)
				print("\t-> Unique Partition GUID : " + self.parts[i].uniquePartGUID)
				print("\t-> First LBA : {} / {}".format(self.parts[i].firstLBA,self.nLBA))
				print("\t-> Last LBA : {} / {}".format(self.parts[i].lastLBA,self.nLBA))
				print("\t-> Flags : " + hex(self.parts[i].flags)[2:])

			print()

			print("\t-> Trying to examine partition inside ...")

			if self.parts[i].type == PartitionType.NTFS:
				print("\t-> NTFS file system found !! Inspecting further ...")
				self.ntfsParts[self.parts[i].SpecialPartID].printinfo()
			else:
				print("\t-> Sadly, nothing was recognized (adding LBAs {} to {} to search scope as UNKNOWN partiton...)".format(self.parts[i].firstLBA,self.parts[i].lastLBA))

class PartitionEntry:
	def __init__(self,im,buffer,size=0x80):
		if len(buffer) != size:
			raise Exception("Size parameter does not match buffer size")
		self.buffer = buffer
		self.size = size
		self.im = im
	def parse(self):
		self.partTypeGUID = ParseNprint.ComputeGUID(self.buffer[:0x10])
		self.uniquePartGUID = ParseNprint.ComputeGUID(self.buffer[0x10:0x20])
		self.firstLBA = unpack("<Q",self.buffer[0x20:0x28])[0]
		self.lastLBA = unpack("<Q",self.buffer[0x28:0x30])[0]
		self.flags = unpack("<Q",self.buffer[0x30:0x38])[0]
		self.name = self.buffer[0x38:0x80].decode("UTF-16LE").strip("\x00")

		self.type = PartitionType.UNKNOWN

		# check type
		if self.im.readBytes(self.firstLBA,0x0,0xb) == b"\xebR\x90NTFS	":
			self.type = PartitionType.NTFS
if __name__ == '__main__':

	img = os.open(filename , os.O_RDONLY | os.O_BINARY)
	myImage = Image(img)
	myImage.recover()
	os.close(img)



