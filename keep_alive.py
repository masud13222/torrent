from flask import Flask, render_template, request, redirect, url_for, jsonify
import os
import logging
from threading import Thread
import signal
import json

app = Flask(__name__)

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'WARNING')  # Default to WARNING
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger('TorrentSeeder')
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.ERROR)  # Only show errors from werkzeug
log_messages = []

# Global variables
seeder_list = []
server_thread = None

def log_message(message):
    log_messages.append(message)
    if len(log_messages) > 100:
        log_messages.pop(0)
    if log_level == 'INFO':
        logger.info(message)
    else:
        logger.debug(message)  # Use debug for less important logs

@app.route('/')
def home():
    torrent_files = []
    if os.path.exists('./torrent'):
        for file in os.listdir('./torrent'):
            if file.endswith('.torrent'):
                torrent_files.append(file)
    return render_template('index.html', torrent_files=torrent_files)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    if file and file.filename.endswith('.torrent'):
        if not os.path.exists('./torrent'):
            os.makedirs('./torrent')
        file.save(os.path.join('./torrent', file.filename))
        log_message(f"Uploaded new torrent file: {file.filename}")
        reload_torrents()
    return redirect(url_for('home'))

@app.route('/delete/<filename>')
def delete_file(filename):
    file_path = os.path.join('./torrent', filename)
    if os.path.exists(file_path):
        # First remove the torrent data
        import torrent
        torrent.Seeder.remove_torrent_data(file_path)
        # Then delete the file
        os.remove(file_path)
        log_message(f"Deleted torrent file: {filename}")
        reload_torrents()
    return redirect(url_for('home'))

@app.route('/logs')
def get_logs():
    return jsonify(logs=log_messages)

@app.route('/peer_data')
def view_peer_data():
    try:
        if os.path.exists('./torrent/peer_data.json'):
            with open('./torrent/peer_data.json', 'r') as f:
                peer_data = json.load(f)
                # Format the JSON data for better readability
                formatted_data = json.dumps(peer_data, indent=2)
                return render_template('peer_data.html', peer_data=formatted_data)
        else:
            return "No peer data found"
    except Exception as e:
        return f"Error reading peer data: {str(e)}"

def shutdown_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()

@app.route('/shutdown')
def shutdown():
    shutdown_server()
    return 'Server shutting down...'

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    global server_thread
    server_thread = Thread(target=run)
    server_thread.daemon = True  # Set thread as daemon
    server_thread.start()

def stop_server():
    try:
        import requests
        requests.get('http://localhost:8080/shutdown')
    except:
        pass

def reload_torrents():
    global seeder_list
    import torrent
    
    seeder_list.clear()
    if os.path.exists('./torrent'):
        for file in os.listdir('./torrent'):
            if file.endswith('.torrent'):
                try:
                    torrent_file = torrent.File('./torrent/' + file)
                    log_message(f"\nProcessing torrent: {file}")
                    log_message(str(torrent_file))

                    seeder = torrent.Seeder(torrent_file)
                    seeder.load_peers()
                    log_message("Seeder info:")
                    log_message(str(seeder))
                    seeder_list.append(seeder)
                except Exception as e:
                    log_message(f"Error processing {file}: {str(e)}")

@app.route('/update_all')
def update_all():
    """Force update all torrents"""
    success_count = 0
    for seeder in seeder_list:
        try:
            if seeder.force_update():
                success_count += 1
                log_message(f"Force updated: {os.path.basename(seeder.torrent.filepath)}")
        except Exception as e:
            log_message(f"Error updating {os.path.basename(seeder.torrent.filepath)}: {str(e)}")
    
    return redirect(url_for('home'))

@app.route('/get_user_agent')
def get_user_agent():
    """Get current user agent"""
    from torrent import Seeder
    return jsonify(user_agent=Seeder.get_user_agent())

@app.route('/set_user_agent', methods=['POST'])
def set_user_agent():
    """Set new user agent"""
    from torrent import Seeder
    user_agent = request.form.get('user_agent')
    if user_agent:
        Seeder.set_user_agent(user_agent)
        log_message(f"Updated User-Agent to: {user_agent}")
    return redirect(url_for('home'))

@app.route('/get_port')
def get_port():
    """Get current port"""
    from torrent import Seeder
    return jsonify(port=Seeder.get_port())

@app.route('/set_port', methods=['POST'])
def set_port():
    """Set new port"""
    from torrent import Seeder
    port = request.form.get('port')
    if port and port.isdigit():
        port = int(port)
        if 1024 <= port <= 65535:  # Valid port range
            Seeder.set_port(port)
            log_message(f"Updated Port to: {port}")
            # Reload torrents to use new port
            reload_torrents()
        else:
            log_message(f"Invalid port number: {port}. Must be between 1024 and 65535")
    return redirect(url_for('home'))

@app.route('/restart')
def restart_server():
    """Restart the server"""
    try:
        log_message("Restarting server...")
        os._exit(1)  # This will trigger supervisor/systemd to restart the process
    except Exception as e:
        log_message(f"Error restarting server: {str(e)}")
    return redirect(url_for('home'))

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)