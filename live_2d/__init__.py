import os

from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.options import define, options, parse_command_line
from tornado.web import Application, RequestHandler

define('port', default=8181, help='port to listen on')

settings = {
    "static_path": os.path.join(os.path.dirname(__file__), "static"),
}

class IndexHandler(RequestHandler):
    def get(self):
        self.render("index.html")

def main():
    """Construct and serve the tornado app"""

    parse_command_line()
    app=Application([(r"/", IndexHandler),
        ],**settings)
    app.listen(options.port)
    print('Listening on http://localhost:%i' % options.port)
    IOLoop.current().start()

if __name__ == "__main__":
    main()
