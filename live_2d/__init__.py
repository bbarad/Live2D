import json
import os

from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.options import define, options, parse_command_line
from tornado.web import Application, RequestHandler
from tornado.websocket import WebSocketHandler

from controls import initialize, load_config

import socket_handlers

define('port', default=8181, help='port to listen on')

# Settings related to actually operating the webpage
settings = {
    "static_path": os.path.join(os.path.dirname(__file__), "static"),
    "static_url_prefix": "/static/",
    "autoreload":"True",
}

config = load_config('latest_run.json')

class SocketHandler(WebSocketHandler):
    def open(self):
        # message_data = initialize_data()
        print("Socket Opened from {}".format(self.request.remote_ip))

    async def on_message(self, message):
        message_json = json.loads(message)
        type = message_json['command']
        data = message_json['data']
        return_data = "Dummy Return"
        if type == 'update_settings':
            for client in SocketHandler.clients:
                client.write_message(return_data)
            pass
        elif type == 'start_job':
            pass
        elif type == 'stop_job':
            pass
        elif type == 'get_gallery':
            pass
        elif type == 'initialize':
            return_data = await initialize(config)
            self.write_message(return_data)
            pass
        else:
            print(message)
            pass

    # def write_message(self, message):
    #
    #     pass

    def on_close(self):
        print("Socket Closed from {}".format(self.request.remote_ip))

class IndexHandler(RequestHandler):
    def get(self):
        self.render("index.html")

# class GalleryHandler(RequestHandler):
#     def get(self):
#         pass


def main():
    """Construct and serve the tornado app"""
    parse_command_line()
    app=Application([(r"/", IndexHandler),
        # (r"/gallery", GalleryHandler),
        (r"/websocket", SocketHandler),
        ],**settings)
    app.listen(options.port)
    print('Listening on http://localhost:%i' % options.port)
    IOLoop.current().start()

if __name__ == "__main__":
    main()
