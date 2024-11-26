from keep_alive import keep_alive, log_message, seeder_list, reload_torrents, stop_server
import os
import time
import signal
import sys
import torrent
import utils
from database import ensure_torrent_dir

# Global flag for graceful shutdown
running = True

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global running
    print("\nShutting down gracefully...")
    log_message("Shutting down gracefully...")
    running = False
    stop_server()

def main():
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Get port from environment variable (for Heroku)
    port = int(os.environ.get('PORT', 8080))
    
    # Create torrent directory if it doesn't exist
    if not os.path.exists('./torrent'):
        os.makedirs('./torrent')
        log_message("Created torrent directory. Please add .torrent files there.")

    # Initial load of torrent files
    reload_torrents()
    
    log_message("\nStarting seeding...")
    
    # Start web server
    from keep_alive import app
    # Use gunicorn for Heroku
    if os.environ.get('HEROKU') == 'true':
        from gunicorn.app.base import BaseApplication
        class StandaloneApplication(BaseApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()
            
            def load_config(self):
                for key, value in self.options.items():
                    self.cfg.set(key, value)

            def load(self):
                return self.application

        options = {
            'bind': f'0.0.0.0:{port}',
            'workers': 1
        }
        StandaloneApplication(app, options).run()
    else:
        # Running locally
        keep_alive()
        
        while running:
            try:
                for seeder in seeder_list:
                    if not running:
                        break
                    if seeder.upload():
                        log_message(f"Updated tracker for {os.path.basename(seeder.torrent.filepath)}")
                        log_message(str(seeder))
                time.sleep(5)
            except Exception as e:
                log_message(f"Error during seeding: {str(e)}")
                time.sleep(5)
                
        log_message("Seeding stopped")
        sys.exit(0)

if __name__ == "__main__":
    main()
