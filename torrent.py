from datetime import datetime
import hashlib 
import struct
import random
import requests
import time
import os
import json

import bencoding
import utils
from database import save_peer_data as db_save_peer_data

PEER_DATA_FILE = './torrent/peer_data.json'
CONFIG_FILE = './torrent/config.json'

class File:
  def __init__(self, filepath):
    self.filepath = filepath
    f = open(filepath, "rb")
    self.raw_torrent = f.read()
    f.close()
    self.torrent_header = bencoding.decode(self.raw_torrent)
    self.announce = self.torrent_header[b"announce"].decode("utf-8")
    torrent_info = self.torrent_header[b"info"]
    m = hashlib.sha1()
    m.update(bencoding.encode(torrent_info))
    self.file_hash = m.digest()

  @property
  def total_size(self):
    size = 0
    torrent_info = self.torrent_header[b"info"]
    if b"files" in torrent_info:
      # Multiple File Mode
      for file_info in torrent_info[b"files"]:
        size += file_info[b"length"]
    else:
      # Single File Mode
      size = torrent_info[b"length"]

    return size

  def __str__(self):
    announce = self.torrent_header[b"announce"].decode("utf-8")
    result = "Announce: %s\n" % announce
        
    if b"creation date" in self.torrent_header:
      creation_date = self.torrent_header[b"creation date"]
      creation_date = datetime.fromtimestamp(creation_date)
      result += "Date: %s\n" % creation_date.strftime("%Y/%m/%d %H:%M:%S")

    if b"created by" in self.torrent_header:
      created_by = self.torrent_header[b"created by"].decode("utf-8")
      result += "Created by: %s\n" % created_by

    if b"encoding" in self.torrent_header:
      encoding = self.torrent_header[b"encoding"].decode("utf-8")
      result += "Encoding: %s\n" % encoding
        
    torrent_info = self.torrent_header[b"info"]
    piece_len = torrent_info[b"piece length"]
    result += "Piece len: %s\n" % utils.sizeof_fmt(piece_len)
    pieces = len(torrent_info[b"pieces"]) / 20
    result += "Pieces: %d\n" % pieces

    torrent_name = torrent_info[b"name"].decode("utf-8")
    result += "Name: %s\n" % torrent_name
    result += "Total Size: %s\n" % utils.sizeof_fmt(self.total_size)

    return result


class Seeder:
  @staticmethod
  def get_user_agent():
    try:
      if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
          config = json.load(f)
          return config.get('user_agent', "qBittorrent 4.3.7")
    except:
      pass
    return "qBittorrent 4.3.7"

  @staticmethod
  def get_port():
    """This is only for display in web UI"""
    try:
      if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
          config = json.load(f)
          return config.get('port', 66856)
    except:
      pass
    return 66856  # Default port

  @staticmethod
  def set_user_agent(user_agent):
    if not os.path.exists('./torrent'):
      os.makedirs('./torrent')
    config = {}
    if os.path.exists(CONFIG_FILE):
      with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    config['user_agent'] = user_agent
    with open(CONFIG_FILE, 'w') as f:
      json.dump(config, f, indent=2)

  @staticmethod
  def set_port(port):
    """This is only for display in web UI"""
    if not os.path.exists('./torrent'):
      os.makedirs('./torrent')
    config = {}
    if os.path.exists(CONFIG_FILE):
      with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    config['port'] = int(port)
    
    # Also update all existing torrents in peer_data
    try:
      if os.path.exists(PEER_DATA_FILE):
        with open(PEER_DATA_FILE, 'r') as f:
          peer_data = json.load(f)
        for torrent_hash in peer_data:
          peer_data[torrent_hash]['port'] = int(port)
        with open(PEER_DATA_FILE, 'w') as f:
          json.dump(peer_data, f, indent=2)
    except:
      pass
            
    with open(CONFIG_FILE, 'w') as f:
      json.dump(config, f, indent=2)

  HTTP_HEADERS = {
    "Accept-Encoding": "gzip",
    "User-Agent": get_user_agent()
  }

  @staticmethod
  def load_or_create_peer_data():
    # Create torrent directory if it doesn't exist
    if not os.path.exists('./torrent'):
      os.makedirs('./torrent')
            
    if os.path.exists(PEER_DATA_FILE):
      try:
        with open(PEER_DATA_FILE, 'r') as f:
          data = json.load(f)
          return data
      except:
        pass
    
    return {}

  @staticmethod
  def save_peer_data(data):
    # Save to MongoDB
    db_save_peer_data(data)
    # Also save locally
    with open(PEER_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

  def __init__(self, torrent):
    self.torrent = torrent
    
    # Load all peer data
    peer_data = self.load_or_create_peer_data()
    
    # Get or create data for this specific torrent
    torrent_hash = hashlib.sha1(self.torrent.file_hash).hexdigest()
    if torrent_hash not in peer_data:
      peer_data[torrent_hash] = {
        'peer_id': "-DE13F0-" + utils.random_id(12),
        'port': 66856,  # Use fixed port
        'key': utils.random_id(12),
        'uploaded': random.randint(30 * 1024 * 1024, 100 * 1024 * 1024)
      }
      self.save_peer_data(peer_data)
    
    torrent_data = peer_data[torrent_hash]
    self.peer_id = torrent_data['peer_id']
    self.port = torrent_data['port']  # Use port from peer_data
    self.download_key = torrent_data['key']
    self.uploaded = torrent_data['uploaded']
    self.downloaded = self.torrent.total_size
    self.last_update = time.time()
    self.next_update = self.get_next_update_time()
    self.torrent_hash = torrent_hash

  @staticmethod
  def remove_torrent_data(filepath):
    """Remove torrent data from peer_data.json"""
    if os.path.exists(PEER_DATA_FILE):
      try:
        # Calculate torrent hash
        with open(filepath, "rb") as f:
          raw_torrent = f.read()
        torrent_header = bencoding.decode(raw_torrent)
        torrent_info = torrent_header[b"info"]
        m = hashlib.sha1()
        m.update(bencoding.encode(torrent_info))
        torrent_hash = hashlib.sha1(m.digest()).hexdigest()
        
        # Remove data for this torrent
        peer_data = Seeder.load_or_create_peer_data()
        if torrent_hash in peer_data:
          del peer_data[torrent_hash]
          Seeder.save_peer_data(peer_data)
          return True
      except:
        pass
    return False

  def get_next_update_time(self):
    """Returns next update time in hours (random between 1-2 hours)"""
    return time.time() + random.uniform(1 * 3600, 2 * 3600)  # Random between 1-2 hours

  def should_update(self):
    """Check if it's time to update"""
    return time.time() >= self.next_update

  def load_peers(self):
    tracker_url = self.torrent.announce
    http_params = {
      "info_hash": self.torrent.file_hash, 
      "peer_id": self.peer_id.encode("ascii"),
      "port": self.port,
      "uploaded": self.uploaded,
      "downloaded": self.downloaded,
      "left": 0,
      "event": "started",
      "key": self.download_key,
      "compact": 1,
      "numwant": 200,
      "supportcrypto": 1,
      "no_peer_id": 1
    }
    try:
      req = requests.get(tracker_url, params=http_params, 
          headers=self.HTTP_HEADERS)
      self.info = bencoding.decode(req.content)
    except Exception as e:
      print(f"Error loading peers: {str(e)}")

  def upload(self):
    if not self.should_update():
      return False

    tracker_url = self.torrent.announce
    http_params = {
      "info_hash": self.torrent.file_hash, 
      "peer_id": self.peer_id.encode("ascii"),
      "port": self.port,
      "uploaded": self.uploaded,
      "downloaded": self.downloaded,
      "left": 0,
      "key": self.download_key,
      "compact": 1,
      "numwant": 0,
      "supportcrypto": 1,
      "no_peer_id": 1
    }
    try:
      requests.get(tracker_url, params=http_params, headers=self.HTTP_HEADERS)
      self.last_update = time.time()
      self.next_update = self.get_next_update_time()
      return True
    except Exception as e:
      print(f"Error during upload: {str(e)}")
      return False

  def __str__(self):
    result = "Peer ID: %s\n" % self.peer_id
    result += "Key: %s\n" % self.download_key
    result += "Port: %d\n" % self.port
    result += "Downloaded: %s\n" % utils.sizeof_fmt(self.downloaded)
    result += "Uploaded: %s\n" % utils.sizeof_fmt(self.uploaded)
    next_update = int((self.next_update - time.time()) / 60)  # Minutes until next update
    result += "Next Update: ~%d minutes\n" % next_update
    return result

  @property
  def peers(self):
    result = []
    peers = self.info[b"peers"]
    for i in range(len(peers)//6):
      ip = peers[i:i+4]
      ip = '.'.join("%d" %x for x in ip)
      port = peers[i+4:i+6]
      port = struct.unpack(">H", port)[0]
      result.append("%s:%d\n" % (ip, port))
    return result

  def force_update(self):
    """Force an immediate update"""
    tracker_url = self.torrent.announce
    http_params = {
        "info_hash": self.torrent.file_hash, 
        "peer_id": self.peer_id.encode("ascii"),
        "port": self.port,
        "uploaded": self.uploaded,
        "downloaded": self.downloaded,
        "left": 0,
        "key": self.download_key,
        "compact": 1,
        "numwant": 0,
        "supportcrypto": 1,
        "no_peer_id": 1
    }
    try:
        # Update HTTP headers with current user agent
        headers = {
            "Accept-Encoding": "gzip",
            "User-Agent": self.get_user_agent()
        }
        
        # Make the request
        requests.get(tracker_url, params=http_params, headers=headers)
        
        # Update timestamps
        self.last_update = time.time()
        self.next_update = self.get_next_update_time()
        
        # Save the current state to peer_data.json
        peer_data = self.load_or_create_peer_data()
        peer_data[self.torrent_hash]['uploaded'] = self.uploaded
        self.save_peer_data(peer_data)
        
        return True
    except Exception as e:
        print(f"Error during force update: {str(e)}")
        return False