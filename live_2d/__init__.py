import os

from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.options import define, options, parse_command_line
from tornado.web import Application, RequestHandler

define('port', default=8181, help='port to listen on')

settings = {
    "static_path": os.path.join(os.path.dirname(__file__), "static"),
    "static_url_prefix": "/static/",
    "autoreload":"True",
}

# Configuration of live processing settings
config = {"job_running": False,
          "warp_folder": "/gne/scratch/u/baradb/",
          "working_directory": "outputdata",
          "galleries": [],
          "logfile": "logfile.txt",
          }

class IndexHandler(RequestHandler):
    def get(self):
        self.render("index.html")

class GalleryHandler(RequestHandler):
    def get(self):
        pass


def main():
    """Construct and serve the tornado app"""

    parse_command_line()
    app=Application([(r"/", IndexHandler),
        (r"/gallery", GalleryHandler),
        ],**settings)
    app.listen(options.port)
    print('Listening on http://localhost:%i' % options.port)
    IOLoop.current().start()

if __name__ == "__main__":
    main()
