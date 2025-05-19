from flask import Flask
from threading import Thread
import signal
import os

app = Flask('')
server_thread = None

@app.route('/')
def home():
    print("Ping received!")
    return "I'm alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    global server_thread
    server_thread = Thread(target=run)
    server_thread.start()

def shutdown():
    os.kill(os.getpid(), signal.SIGINT)
