#!/usr/bin/python

###############################################################################
#
# File: photo_db.py 
#
# Date: 4/1/2015
#
# Author: Adam Kelson
#
###############################################################################

import sys
import StringIO
from PIL import Image
import imagehash
import sqlite3
import datetime
import os
from os import walk
import re
import zlib

try:
    import cPickle as pickle
except:
    import pickle

###############################################################################
# Class: PhotoDb
###############################################################################
class PhotoDb:

    # -------------------------------------------------------------------------
    def __init__(self,db_path):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.c = self.conn.cursor()

    # -------------------------------------------------------------------------
    def __del__(self):
        self.conn.close()

    # -------------------------------------------------------------------------
    # Description: Generate photo info for a photo. Check if the photo is 
    #     already in the photos table and add it if necessary.
    # -------------------------------------------------------------------------
    def AddPhoto(self,photo_string,crc):
        photo_info = PhotoInfo(photo_string)

        photo_id = self.FindPhotoIdByCrcHash(crc, photo_info.GetHash() )

        if None == photo_id:
            thumb_blob = sqlite3.Binary(photo_info.GetThumb())
            pickle_string = StringIO.StringIO()
            exif_pickle = pickle.dump(photo_info.exif, pickle_string)
            exif_blob = sqlite3.Binary(pickle_string.getvalue())
            self.c.execute(
                """INSERT INTO photos(exif,crc,micro_thumb,hash) 
                   VALUES (?,?,?,?)""",
                (exif_blob,crc, thumb_blob, photo_info.GetHash()))
            photo_id = self.c.lastrowid

        return photo_id

    # -------------------------------------------------------------------------
    # Description: Find a photo ID in by file name and CRC.
    # -------------------------------------------------------------------------
    def FindPhotoId(self, name, crc):
        self.c.execute(
            """SELECT photos.uid 
               FROM files JOIN photos ON files.photo_id=photos.uid
               WHERE photos.crc=? AND files.name=?""",
               (crc, name))
        row = self.c.fetchone()
        if None == row:
            return None
        else:
            return row[0]

    # -------------------------------------------------------------------------
    def FindPhotoIdByCrcHash(self, crc, photoHash):
        self.c.execute(
            """SELECT uid 
               FROM photos
               WHERE crc=? AND hash=?""",
               (crc, photoHash))
        row = self.c.fetchone()
        if None == row:
            return None
        else:
            return row[0]

    # -------------------------------------------------------------------------
    def AddFile(self, collName, photoPath, rootPath):
        mtime = os.path.getmtime(photoPath)
        ctime = os.path.getctime(photoPath)
        rel_path = os.path.relpath(photoPath, rootPath)
        photo_name = os.path.basename(photoPath)

        try:
            with open(photoPath, 'rb') as f:
                photo_string = StringIO.StringIO(f.read())
                crc = zlib.adler32(photo_string.getvalue())
        except:
            print
            print "Failed to open", photoPath
            return

        photo_id = self.FindPhotoId(photo_name,crc)

        if None == photo_id:
            photo_id = self.AddPhoto(photo_string,crc)

        self.c.execute(
            """INSERT INTO 
               files(photo_id,collection_id,path,name,ctime,mtime) 
               VALUES 
                   (?,
                   ( SELECT uid FROM collections WHERE name=? ),
                   ?,?,?,?)""",
            (photo_id,collName,os.path.dirname(rel_path),photo_name,
             ctime,mtime))

        self.conn.commit()

    # -------------------------------------------------------------------------
    @staticmethod
    def GetCollectionPhotoPaths(rootPath):
        photo_pattern = re.compile(r".*\.(jpg|jpeg)$", re.IGNORECASE)
        photo_paths = []

        for (dirpath, dirnames, filenames) in walk(rootPath):
            photo_names = filter(photo_pattern.search, filenames)
            photo_names = [p for p in photo_names if p[0] != '.']
            for photo_name in photo_names: 
                photo_paths.append( os.path.join( dirpath, photo_name ) )

        return photo_paths

    # -------------------------------------------------------------------------
    def AddCollection(self,name,desc,rootPath):

        if self.CollectionExists(name):
            print "A collection with the name '%s' already exists." % (name)
            return

        self.c.execute(
            """INSERT INTO collections(name,desc,date_created,date_modified) 
               VALUES (?,?,?,?)""",
            (name, desc, datetime.datetime.now(), datetime.datetime.now()))
        collection_id = self.c.lastrowid

        photo_paths = PhotoDb.GetCollectionPhotoPaths(rootPath)
        count = 1
        num_photos = len(photo_paths)
        for photo_path in photo_paths:
            percent = int((count * 100)/num_photos)
            sys.stdout.write("\r%d%% %i/%i - %s " % 
                (percent,count,num_photos,photo_path))
            sys.stdout.flush()
            try:
                self.AddFile(name, photo_path, rootPath)
            except:
                print "Failed to add file '%s'" % photo_path
            count += 1
    
    # -------------------------------------------------------------------------
    def CollectionExists(self,collName):
        self.c.execute(
            """SELECT uid FROM collections WHERE name=?""",
            (collName,))
        if None == self.c.fetchone():
            return False
        else:
            return True

    # -------------------------------------------------------------------------
    def UpadateCollection(self, collName, rootPath):
        # Find missing and modified files
        print "Checking for removed or modified photos."
        (missing_list, modified_list, verified_list) = self.VerifyQuick(
            collName, rootPath)

        verified_paths = []
        for (ver_photo_id, ver_photo_name, ver_photo_path) in verified_list:
            verified_paths.append(os.path.join(ver_photo_path, ver_photo_name))

        # Find all files in root path
        print "Building list of all photos."
        photo_paths = PhotoDb.GetCollectionPhotoPaths(rootPath)

        print "Checking for new photos."
        added_files = []
        for photo_path in photo_paths:
            relpath = os.path.relpath(photo_path, rootPath)
            #Check if file is new
            if not os.path.relpath(photo_path, rootPath) in verified_paths:
                added_files.append(photo_path)
        
        count = 1
        num_photos = len(added_files)
        for added_file in added_files:
            percent = int((count * 100)/num_photos)
            sys.stdout.write("\r%d%% %i/%i - %s " % 
                (percent,count,num_photos,added_file))
            sys.stdout.flush()
            try:
                self.AddFile(collName, added_file, rootPath)
            except:
                print "Failed to add file '%s'" % added_file
            count += 1

    # -------------------------------------------------------------------------
    def VerifyQuick(self, collName, rootPath):
        missing_list = []
        modified_list = []
        verified_list = []

        self.c.execute(
            """SELECT files.photo_id, files.name, files.path, files.mtime 
               FROM files JOIN 
                   collections ON files.collection_id=collections.uid 
               WHERE collections.name=?""",
            (collName,))

        for (photo_id, photo_name, path, mtime) in self.c.fetchall():
            photo_path = os.path.join(rootPath,path,photo_name)
            if not os.path.exists(photo_path):
                missing_list.append((photo_id, photo_name, path))
                print "Missing:", os.path.relpath(photo_path,rootPath)
            elif mtime != os.path.getmtime(photo_path):
                modified_list.append((photo_id, photo_name, path))
                print "Modified:", os.path.relpath(photo_path,rootPath)
            else:
                verified_list.append((photo_id, photo_name, path))

        return (missing_list, modified_list, verified_list)

    # -------------------------------------------------------------------------
    def GetThumbByPhotoId(self,photoId):
        self.c.execute(
            """SELECT micro_thumb FROM photos WHERE uid=?""",
            (photoId,))
        thumb_blob = self.c.fetchone()[0]
        return thumb_blob

###############################################################################
# Class: PhotoInfo
###############################################################################
class PhotoInfo:

    # -------------------------------------------------------------------------
    def __init__(self, photo_string):
        self.img = Image.open(photo_string)
        try:
            self.exif = self.img._getexif()
        except:
            self.exif = None
        self.hash_value = None
        self.thumb_string = None

    # -------------------------------------------------------------------------
    def Compare(self,other):
        return False

    # -------------------------------------------------------------------------
    def GetThumb(self):
        if None == self.thumb_string:
            thumb_img = self.img
            thumb_img.thumbnail((64,64), Image.NEAREST)
            self.thumb_string = StringIO.StringIO()
            thumb_img.save(self.thumb_string, "GIF")
        return self.thumb_string.getvalue()

    # -------------------------------------------------------------------------
    def GetHash(self):
        if None == self.hash_value:
            self.hash_value = str(imagehash.average_hash(self.img))
        return self.hash_value


    # -------------------------------------------------------------------------
    def GetDate(self):
        if self.exif and 36867 in self.exif:
            return self.exif[36867]
        else:
            return None

