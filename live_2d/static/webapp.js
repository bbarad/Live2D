
var uri=""

// Display Utilities go below here - just random stuff to make pretty things happen.
$(document).ready(function () {
  $('[rel="popover"]').popover(
    {container: 'body'}
  )
  $('[rel="tooltip"]').tooltip(
    {container: 'body'}
  )

  if(window.WebSocket) {
    start_websocket()
    // control_websocket()
  }
  else {
    bootbox.alert({message: "This Browser Does Not Support Websockets... Try recent versions of chrome, safari, or firefox!",
                  backdrop: false
                });
  }

  function start_websocket() {
    if (window.location.port == null){
      ws_url = "ws://" + window.location.hostname + "/websocket"
    } else {
      ws_url = "ws://" + window.location.hostname + ":"+window.location.port+"/websocket"
    }
    // bootbox.alert(ws_url)
    var ws = new WebSocket(ws_url);
    ws.onopen = function(){
                          ws.send(JSON.stringify({command:"initialize", data:{}}));
    }
    ws.onmessage = function(msg){
      data_object = JSON.parse(msg.data)
      switch(data_object.type) {
        default:
          bootbox.alert("Didn't understand the message type "+data_object.type)
      }
    }
  }
})

function set_vars(uri_from_server){
  uri = uri_from_server;
}

//
// $(document).on('click', '[data-toggle="lightbox"]', function(event) {
//                 event.preventDefault();
//                 $(this).ekkoLightbox();
// });
