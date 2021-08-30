from struct import unpack, pack
import Partitions.ParseNprint as ParseNprint
from parseIMG import DEV
class ntfsPart:
	def __init__(self,im,start,end,partid):
		self.im = im 
		self.start = start
		self.end = end 

		assert self.im.readBytes(self.start,0x0,0xb) == b"\xebR\x90NTFS    "

		self.header = self.im.nthLBA(self.start)
	def printinfo(self):
		print("\t\t-> NTFS journaling file system")
		print("\t\t-> Part size : {} Sectors or {} Bytes or {} Gb which is {}".format(self.partSizeInSector,ParseNprint.groupby3(self.size),round(self.size/10**9,2),self.size == (self.end - self.start)*self.im.lba_size))

		print()

		if DEV:
			print("\t\t-> Sector size : {} Bytes".format(self.sectorSize))
			print("\t\t-> Number of sectors per Cluster : {}".format(self.sectorPerCluster))
			print("\t\t-> Type of drive : {} ".format("0x"+hex(self.typeOfDrive)[2:].upper()))
			print("\t\t-> Number of sectors per Track : {}".format(self.sectorPerTrack))
			print("\t\t-> Number of heads on the drive : {}".format(self.numHeads))

			print()

			print("\t\t-> Number of Sectors before this : {} which is {}".format(self.sectorBeforePart,self.sectorBeforePart == self.start))

			print("\t\t-> $MFT Cluster : {} Cluster".format(ParseNprint.engnumsufix(self.MFTCluster)))
			print("\t\t-> $MFTMirr (backup) Cluster : {} Cluster".format(ParseNprint.engnumsufix(self.MFTMirrCluster)))

			print()

			print("\t\t-> Unique Volume Serial Number : {}".format(hex(self.VolumeSerialNum)))

		for i in range(len(self.MFTrecords)):
			if i < 64:
				continue	
			if DEV:
				print("\t\t\t-> MFT Record {} of size {} / {} with name {} and flag {} at (offset and size) : {}".format(
					i,
					self.MFTrecords[i].usedSizeMFTentry,
					self.MFTrecords[i].allocatedSizeMFTentry,
					self.MFTrecords[i].fileName,
					self.MFTrecords[i].flags,
					self.MFTrecords[i].data))
		if DEV :
			print("\n\n")
		for f in self.files:
			if f.deleted:
				_ss = "deleted (but recoverable)"
			else:
				_ss = "present"
			print("\t\t\t-> Entry named {} as size {} and is a {} which is {} and begin with {} ".format(
					f.fileName,
					f.size,
					f.type,
					_ss,
					str(f.getNBytes(10))[2:-1] ))
	def parseMTF(self):
		self.MFT1stCluster = self.nthCluster(self.MFTCluster)
		self.MFTMirr1stCluster = self.nthCluster(self.MFTMirrCluster)

		self.MFTrecords = []
		i = 0
		while True:
			_rec = self.nthRecordSegment(i)
			if _rec[:4] == b"FILE":
				_tempMFTrec = MFRrecord(_rec,self.im,self.start*self.im.lba_size + self.MFTCluster*self.bytesPerCluster + i*self.bytesPerFileRecordSegment,self)
				_tempMFTrec.parse()
				self.MFTrecords.append(_tempMFTrec)
			else:
				break
			i += 1

		self.files = []
		for i in range(64,len(self.MFTrecords)):
			self.files.append(self.parseFile(self.MFTrecords[i]))

	def parseFile(self,record):
		_rm = bool((record.flags & 1) ^ 1)
		if record.flags >> 1:
			_ty = "folder"
		else:
			_ty = "file"
		return File(record.fileName,record.data,_ty,_rm,self.im)
	def nthCluster(self,n):
		return self.im.readB(self.start*self.im.lba_size + n*self.bytesPerCluster,self.bytesPerCluster)

	def nthRecordSegment(self,n):
		return self.im.readB(self.start*self.im.lba_size + self.MFTCluster*self.bytesPerCluster + n*self.bytesPerFileRecordSegment,self.bytesPerFileRecordSegment)

	def parse(self):

		self.sectorSize = unpack("H",self.header[0x0B:0x0D])[0]
		self.sectorPerCluster = unpack("b",self.header[0x0D:0x0E])[0]
		if self.sectorPerCluster < 0:
			self.sectorPerCluster = pow(2,abs(self.sectorPerCluster))
		self.bytesPerCluster = self.sectorPerCluster*self.sectorSize

		assert unpack("I",self.header[0x0E:0x12])[0] == 0
		assert unpack("H",self.header[0x12:0x14])[0] == 0
		assert unpack("B",self.header[0x14:0x15])[0] == 0

		self.typeOfDrive = unpack("B",self.header[0x15:0x16])[0]

		assert unpack("H",self.header[0x16:0x18])[0] == 0

		self.sectorPerTrack = unpack("H",self.header[0x18:0x1A])[0]
		self.numHeads = unpack("H",self.header[0x1A:0x1C])[0]
		self.sectorBeforePart = unpack("I",self.header[0x1C:0x20])[0]

		self.partSizeInSector = unpack("Q",self.header[0x28:0x30])[0]
		self.size = self.partSizeInSector*self.sectorSize

	
		self.MFTCluster = unpack("Q",self.header[0x30:0x38])[0]
		self.MFTMirrCluster = unpack("Q",self.header[0x38:0x40])[0]

		_t = unpack("b",self.header[0x40:0x41])[0]
		if _t > 0:
			self.clustersPerFileRecordSegment = _t 
			self.bytesPerFileRecordSegment = self.clustersPerFileRecordSegment * self.bytesPerCluster	
		else:
			self.bytesPerFileRecordSegment = 2**abs(_t)

		_t = unpack("b",self.header[0x44:0x45])[0]
		if _t > 0:
			self.clustersPerIndexBuffer = _t 
			self.bytesPerIndexBuffer = self.clustersPerIndexBuffer*self.bytesPerCluster
		else:
			self.bytesPerIndexBuffer = 2**abs(_t) 
			
		self.VolumeSerialNum = unpack("Q",self.header[0x48:0x50])[0]
		assert unpack("H",self.header[0x01FE:0x0200])[0] == 0xAA55

		self.parseMTF()

class MFRrecord:
	def __init__(self,record,im,addr,ntfsPartRef):
		self.rec = record	
		self.im = im
		self.addr = addr
		self.ntfsPartRef = ntfsPartRef

	def parse(self):
		assert self.rec[0x0:0x4] == b"FILE"
		self.updateSequenceOffset = unpack("H",self.rec[0x4:0x6])[0]
		self.numEntriesInFixupArray = unpack("H",self.rec[0x6:0x8])[0]
		self.logFileSeqNum = unpack("Q",self.rec[0x8:0x10])[0]
		self.seqNum = unpack("H",self.rec[0x10:0x12])[0]

		self.hardLinkCount = unpack("H",self.rec[0x12:0x14])[0]
		self.firstAttributeOffset = unpack("H",self.rec[0x14:0x16])[0]
		self.flags = unpack("H",self.rec[0x16:0x18])[0]

		self.usedSizeMFTentry = unpack("I",self.rec[0x18:0x1C])[0]
		self.allocatedSizeMFTentry = unpack("I",self.rec[0x1C:0x20])[0]

		self.fileRefToBaseFileRecord = unpack("Q",self.rec[0x20:0x28])[0]
		self.nextAttributeID = unpack("H",self.rec[0x28:0x2A])[0]
		self.nalignTo4B = unpack("H",self.rec[0x2A:0x2C])[0]

		self.numOfThisMTFrec = unpack("I",self.rec[0x2C:0x30])[0]


		self.attributes = []

		_currentAttribLocation = self.firstAttributeOffset

		i = 0
		while True: ## record every attributes
			if len(self.rec[_currentAttribLocation:_currentAttribLocation+0x04]) != 4:
				break
			_attribID = unpack("I",self.rec[_currentAttribLocation:_currentAttribLocation+0x04])[0]
			if _attribID == 0xffffffff:
				break

			_attribLen = unpack("I",self.rec[_currentAttribLocation+0x4:_currentAttribLocation+0x08])[0]
			_tAttribute = MFTattribute(self.numOfThisMTFrec,self.rec[_currentAttribLocation:_currentAttribLocation+_attribLen],self.im,self.addr+_currentAttribLocation,self.ntfsPartRef)

			_tAttribute.parse()
			self.attributes.append(_tAttribute)

			_currentAttribLocation += _attribLen
			i += 1

		self.fileName = "UNKNOWN"
		self.data = [(0 , 0)]

		for _att in self.attributes:
			if _att.type == "$FILENAME":
				self.fileName = _att.fileName
			elif _att.type == "$DATA":
				self.data = _att.data
			#elif _att.type == "$UNKNOWN":
				#print("Unrecognised attrib ID on MFT nb {} : {}".format(_att.MFTnumber,hex(_att.attribID)))
class MFTattribute:
	def __init__(self,MFTnumber,attrib,im,addr,ntfsPartRef):
		self.MFTnumber = MFTnumber
		self.attrib = attrib
		self.im = im
		self.addr = addr
		self.ntfsPartRef = ntfsPartRef
		self.type = "$UNKNOWN"

	def parse(self):
		self.attribID = unpack("I",self.attrib[0:0x04])[0]
		self.attribLen = unpack("I",self.attrib[0x4:0x08])[0]

		self.resident = unpack("B",self.attrib[0x8:0x9])[0]

		if not self.resident:
			self.contentSize = unpack("I",self.attrib[0x10:0x14])[0]
			self.contentOffset = unpack("H",self.attrib[0x14:0x16])[0]

		if self.attribID == 0x30: # $FILENAME
			self.parseFILENAME()
		elif self.attribID == 0x80: # $DATA
			self.parseDATA()
			
	def parseFILENAME(self):
		self.type = "$FILENAME"

		self.fileNameLen = unpack("B",self.attrib[self.contentOffset + 0x40:self.contentOffset + 0x41])[0]
		self.fileName = self.attrib[self.contentOffset + 0x42:self.contentOffset + 2*self.fileNameLen + 0x42].decode("UTF-16LE")

	def parseDATA(self):
		self.type = "$DATA"

		if not self.resident:
			self.dataSize = self.contentSize
			self.data = [(self.addr+self.contentOffset,self.dataSize)]
			#self.data = self.attrib[self.contentOffset:self.contentOffset + self.dataSize]
		else:
			self.flags = unpack("H",self.attrib[0x0C:0x0E])[0]

			if self.flags == 0x0000: # normal data
				data = self.unpackData()
			elif self.flags == 0x4000: # Encrypted
				self.data = (0,0) #"Data is encrypted !!"
			elif self.flags == 0x8000: # Sparse
				self.data = (0,0) #"Sparse data not supported"
			elif self.flags == 0x0001: # Sparse
				self.data = (0,0) #"Compressed data not supported"
			else: 
				self.data = (0,0) #"Data error"

	def unpackData(self):
		self.initVirtualClusterNum = unpack("Q",self.attrib[0x10:0x18])[0]
		self.finalVirtualClusterNum = unpack("Q",self.attrib[0x18:0x20])[0]

		self.dataRunsOffset = unpack("H",self.attrib[0x20:0x22])[0]
		self.compressionUnit = unpack("H",self.attrib[0x22:0x24])[0]

		if self.compressionUnit == 0:
			self.fileAllocSize = unpack("Q",self.attrib[0x28:0x30])[0]
			self.fileRealSize = unpack("Q",self.attrib[0x30:0x38])[0]

			self.initialFileSize = unpack("Q",self.attrib[0x38:0x40])[0]

			if self.initialFileSize ==  self.fileRealSize:

				_dataRunsAddr = self.dataRunsOffset
				self.data = [] ## an array containing tuples of (addr, offset) for each data run

				_dataRun = unpack("B",self.attrib[_dataRunsAddr:_dataRunsAddr+1])[0]
				while _dataRun != 0x00:
					_dataRunl1 = (_dataRun & 0xf0) >> 0x04
					_dataRunl2 = _dataRun & 0x0f
	
					_dataBlockSizeInCluster = self.attrib[_dataRunsAddr + 1:_dataRunsAddr + _dataRunl2 + 1]
					_dataBlockOffsetInCluster = self.attrib[_dataRunsAddr + _dataRunl2 + 1:_dataRunsAddr + _dataRunl2 + _dataRunl1 + 1]
	
					self.dataOffset = int(_dataBlockOffsetInCluster.hex(),16)
					self.dataOffset = ParseNprint.switchEndian(self.dataOffset)

					self.dataSizeInCluster = int(_dataBlockSizeInCluster.hex(),16)
	
					self.dataAddr = self.ntfsPartRef.start*self.im.lba_size + self.dataOffset*self.ntfsPartRef.bytesPerCluster
					self.dataSize = self.dataSizeInCluster*self.ntfsPartRef.bytesPerCluster
	
					self.data.append((self.dataAddr,self.dataSize))

					_dataRunsAddr += _dataRunl1 + _dataRunl2 + 1
					_dataRun = unpack("B",self.attrib[_dataRunsAddr:_dataRunsAddr+1])[0]

			else:
				self.data = "Changed size file not supported" # TODO
		else:
			self.data = "Compressed data not supported" # TODO



class File:
	def __init__(self,fileName,data,ty,deleted,im):
		self.fileName = fileName

		self.data = data

		self.type = ty
		self.deleted = deleted

		self.im = im

		self.size = 0
		if self.type == "file":
			for d in self.data:
				try:
					self.size += d[1]
					assert len(d) == 2
				except Exception as e:
					print(d,"\n",e)
				
	def getData(self):
		d = b""
		for el in self.data:
			d += self.im.readB(el[0],el[1])
		return d
	def getNBytes(self,n):
		d = b""
		for el in self.data:
			if el[1] >= n:
				d += self.im.readB(el[0],n)
				return d
			else:
				d += self.im.readB(el[0],el[1])
				n -= el[1]
		#print("Warning, something is off ... returning anyway")
		return d

