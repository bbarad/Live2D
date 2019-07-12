
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
        case "init":
          get_settings_from_server(data_object.settings);
          update_class_gallery(data_object.gallery_data);
        default:
          // bootbox.alert("Didn't understand the message type "+data_object.type)
      }
    }
  }
  function get_settings_from_server(settings) {
    $("#warp-directory").val(settings.warp_folder);
    $("#neural-net").val(settings.neural_net);
    $("#pixel-size").val(settings.pixel_size);
    $("#mask-radius").val(settings.mask_radius);
    $("#" + settings.classification_type).click();
    $("#high-res-initial").val(settings.high_res_initial);
    $("#high-res-final").val(settings.high_res_final);
    $("#startup-cycle-count").val(settings.run_count_startup);
    $("#refinement-cycle-count").val(settings.run_count_refine);
    $("#start-count").val(settings.particle_count_initial);
    $("#update-count").val(settings.particle_count_update);
    $("#number-classes").val(settings.class_number);
    $("#number-per-class").val(settings.particles_per_class);
    $("#autocenter").prop("checked", settings.autocenter);
    $("#automask").prop("checked", settings.automask)
    // bootbox.alert("settings: "+settings)
  }

  function send_settings_to_server(settings) {}

  function update_class_gallery(data) {
    // bootbox.alert("gallery data "+data)
    $("#class-gallery").html(data);
    // $("#class-gallery").collapse();
    $(document).on('click', '[data-toggle="lightbox"]', function(event) {
                  event.preventDefault();
                  $(this).ekkoLightbox();
    });
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
