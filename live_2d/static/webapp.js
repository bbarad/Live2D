
var uri=""

// Display Utilities go below here - just random stuff to make pretty things happen.
$(document).ready(function () {
  $('[rel="popover"]').popover(
    {container: 'body'}
  );


  if(window.WebSocket) {
    start_websocket();
    // control_websocket()
  }
  else {
    bootbox.alert({message: "This Browser Does Not Support Websockets... Try recent versions of chrome, safari, or firefox!",
                  backdrop: false
                });
  }

  $("#console").scrollTop = 1500;

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
    };
    ws.onmessage = function(msg){
      data_object = JSON.parse(msg.data)
      switch(data_object.type) {
        case "init":
          console.log(data_object.settings);
          get_settings_from_server(data_object.settings);
          update_class_gallery(data_object.gallery_data);
          break;
        case "console_update":
          get_console_from_server(data_object.data);
          break;
        case "gallery_update":
          update_class_gallery(data_object.gallery_data);
          break;
        case "settings_update":
          get_settings_from_server(data_object.settings);
          break;
        case "job_started":
          bootbox.alert("You successfully started a job");
          $("#job-status").html("Started").show();
          // console.log(data_object.settings)
          // get_settings_from_server(data_object.settings);
          break;
        case "job_finished":
          $("#job-status").html("Stopped").show();
          break;
        case "kill_received":
          $("#job-status").html("Killing").show();
          bootbox.alert("A user has killed the current job. It will finish after the current cycle is complete.")
          break;
        case "alert":
          bootbox.alert(data_object.data);
          break;
        default:
          // bootbox.alert("Didn't understand the message type "+data_object.type)
      }
    };
    // $(document).off('click',"#submit-settings");
    // $(document).on('click', '#submit-settings', function(event) {
    //               event.preventDefault();
    //               message = send_settings_to_server();
    //               ws.send(JSON.stringify(message));
    // });
    $(document).off('click',"#start-job");
    $(document).on('click', '#start-job', function(event) {
                  event.preventDefault();
                  $('#start-job').popover('hide');
                  message = send_settings_and_start_job();
                  ws.send(JSON.stringify(message));

    });
    $(document).off('click',"#stop-job");
    $(document).on('click', '#stop-job', function(event) {
                  event.preventDefault();
                  message = {"command": "kill_job", "data": "Kill this job!"}

                  ws.send(JSON.stringify(message));
    });
    $(document).off('click',"#update-warp-directory");
    $(document).on('click', '#update-warp-directory', function(event) {
                  event.preventDefault();
                  message = {"command": "change_directory", "data": $("#warp-directory").val()};
                  console.log(message);
                  ws.send(JSON.stringify(message));
    });

    $(document).off('click',"[class*='page-link']");
    $(document).on("click", "[class*='page-link']" ,function(event) {
      event.preventDefault();
      ws.send(JSON.stringify({command: "get_gallery", data: {gallery_number: $(event.target).attr("value")}
      }));
    });

    $(document).off('change', '#class-selector');
    $(document).on('change', '#class-selector', function() {
      event.preventDefault();
      console.log($(this).val());
      ws.send(JSON.stringify({command: "get_gallery", data: {gallery_number: $(this).val()}
      }));
    });

    $(document).off('click',"[data-toggle='lightbox']");
    $(document).on('click', '[data-toggle="lightbox"]', function(event) {
                    event.preventDefault();
                    $(this).ekkoLightbox();
    });
  }



  function get_settings_from_server(settings) {
    $("#warp-directory").val(settings.warp_folder);
    $("#neural-net").val(settings.settings.neural_net);
    $("#pixel-size").val(settings.settings.pixel_size);
    $("#mask-radius").val(settings.settings.mask_radius);
    $("#" + settings.settings.classification_type).click();
    $("#high-res-initial").val(settings.settings.high_res_initial);
    $("#high-res-final").val(settings.settings.high_res_final);
    $("#startup-cycle-count").val(settings.settings.run_count_startup);
    $("#refinement-cycle-count").val(settings.settings.run_count_refine);
    $("#start-count").val(settings.settings.particle_count_initial);
    $("#update-count").val(settings.settings.particle_count_update);
    $("#number-classes").val(settings.settings.class_number);
    $("#number-per-class").val(settings.settings.particles_per_class);
    $("#autocenter").prop("checked", settings.settings.autocenter);
    $("#automask").prop("checked", settings.settings.automask).show()
    switch (settings.job_status) {
      case "running":
        $("#job-status").html("Running");
        $( "#update-warp-directory" ).prop( "disabled", true );
        $('#update-warp_directory').popover('hide');
        $( "#start-job" ).prop( "disabled", true );
        $('#start-job').popover('hide');
        $( "#stop-job" ).prop( "disabled", false );
        break;
      case "listening":
        $("#job-status").html("Waiting for New Particles");
        $( "#update-warp-directory" ).prop( "disabled", false );
        $( "#start-job" ).prop( "disabled", false );
        $( "#stop-job" ).prop( "disabled", true );
        $('#stop-job').popover('hide');
        break;
      case "stopped":
        $("#job-status").html("Ready for New Runs");
        $( "#update-warp-directory" ).prop( "disabled", false );
        $( "#start-job" ).prop( "disabled", false );
        $( "#stop-job" ).prop( "disabled", true );
        $('#stop-job').popover('hide');
        break;
      case "killed":
        $("#job-status").html("Waiting to Kill");
        $( "#update-warp-directory" ).prop( "disabled", true );
        $("#update-warp-directory").popover('hide');
        $( "#start-job" ).prop( "disabled", true );
        $('#start-job').popover('hide');

        $( "#stop-job" ).prop( "disabled", true );
        $('#stop-job').popover('hide');

        break;
      default:
        bootbox.alert("Something is wrong with the job-status setting: "+settings.job_status)

    }

    // bootbox.alert("settings: "+settings)
  }

  function change_warp_directory(directory) {
    message = {command: "change_directory", data: directory};
    return message;
  }

  function send_settings_and_start_job() {
    message = {command: "start_job",
              data: {}
    }
    // message.data.warp-folder = $('#warp-directory').val();
    message.data.neural_net = $("#neural-net").val();
    message.data.pixel_size = $("#pixel-size").val();
    message.data.mask_radius=$("#mask-radius").val();
    message.data.classification_type = $("input[name='classification-type']:checked").val();
    message.data.high_res_initial =$("#high-res-initial").val();
    message.data.high_res_final = $("#high-res-final").val();
    message.data.run_count_startup = $("#startup-cycle-count").val();
    message.data.run_count_refine = $("#refinement-cycle-count").val();
    message.data.particle_count_initial = $("#start-count").val();
    message.data.particle_count_update = $("#update-count").val();
    message.data.class_number = $("#number-classes").val();
    message.data.particles_per_class = $("#number-per-class").val();
    message.data.automask = $("#automask").prop("checked");
    message.data.autocenter = $("#autocenter").prop("checked");
    return message;
    }

  function get_console_from_server(data) {
    $("#console").html(data)
  }

  function update_class_gallery(data) {
    $('nav *').tooltip('hide')
    // bootbox.alert("gallery data "+data)
    $("#class-gallery").html(data);
    $('[data-toggle="tooltip"]').tooltip(
      {container: 'body',
      placement: 'bottom'}
    );
    // adjust_galleries_shown();
  }

  // function adjust_galleries_shown() {
  //   curgal = parseInt($(".pagination > li.active").text(), 10);
  //   console.log(curgal);
  //   gal_len = $("[class*='page-item']").length;
  //   console.log(gal_len);
  //   $.each($("[class*='page-item']"), function (index, value) {
  //     $(this).hide();
  //     if ([0,1,2].includes(index)) {
  //       $(this).show();
  //     }
  //     else if ([gal_len-1, gal_len-2, gal_len-3].includes(index)) {
  //       $(this).show();
  //     }
  //     else if (Math.abs(parseInt($(this).text(),10) - curgal) < 4) {
  //       $(this).show();
  //     }
  //   });
  // }


})

function set_vars(uri_from_server){
  uri = uri_from_server;
}

//
// $(document).on('click', '[data-toggle="lightbox"]', function(event) {
//                 event.preventDefault();
//                 $(this).ekkoLightbox();
// });
