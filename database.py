from pymongo import MongoClient
import json
import bson
import os
import shutil

# MongoDB connection
MONGODB_URI = "mongodb+srv://cinemazbd:A3cyYdaS3JkOGYog@cluster0.akey0.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGODB_URI)
db = client['torrent_seeder']

def save_torrent_file(filename, file_data):
    """Save torrent file to MongoDB"""
    collection = db['torrent_files']
    # Convert binary data to BSON binary
    binary_data = bson.Binary(file_data)
    document = {
        'filename': filename,
        'data': binary_data
    }
    collection.replace_one({'filename': filename}, document, upsert=True)

def get_torrent_files():
    """Get all torrent files from MongoDB"""
    collection = db['torrent_files']
    return list(collection.find())

def delete_torrent_file(filename):
    """Delete torrent file from MongoDB"""
    collection = db['torrent_files']
    collection.delete_one({'filename': filename})

def save_peer_data(data):
    """Save peer data to MongoDB"""
    collection = db['peer_data']
    collection.replace_one({}, {'data': data}, upsert=True)

def get_peer_data():
    """Get peer data from MongoDB"""
    collection = db['peer_data']
    doc = collection.find_one()
    return doc['data'] if doc else {}

def ensure_torrent_dir():
    """Ensure torrent directory exists and restore files from MongoDB"""
    # First remove existing torrent directory
    if os.path.exists('./torrent'):
        shutil.rmtree('./torrent')
    
    # Create fresh torrent directory
    os.makedirs('./torrent')
    
    # Restore torrent files from MongoDB
    for doc in get_torrent_files():
        try:
            filename = doc['filename']
            file_data = doc['data']
            file_path = os.path.join('./torrent', filename)
            with open(file_path, 'wb') as f:
                f.write(file_data)
        except Exception as e:
            print(f"Error restoring {filename}: {str(e)}")
    
    # Restore peer data
    peer_data = get_peer_data()
    if peer_data:
        with open('./torrent/peer_data.json', 'w') as f:
            json.dump(peer_data, f, indent=2) 
