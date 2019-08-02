
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
          break;
        case "job_finished":
          $("#job-status").html("Stopped").show();
          break;
        case "kill_received":
          $("#job-status").html("Killing").show();
          bootbox.alert("A user has killed the current job. It will finish after the current cycle is complete.")
          $("#job-status").html("Waiting to Kill");
          $( "#update-warp-directory" ).prop( "disabled", true );
          $("#update-warp-directory").popover('hide');
          $( "#start-job" ).prop( "disabled", true );
          $('#start-job').popover('hide');
          $( "#start-listening" ).prop( "disabled", true );
          $('#start-listening').popover("hide");
          $( "#stop-job" ).prop( "disabled", true );
          $('#stop-job').popover('hide');
          break;
        case "alert":
          bootbox.alert(data_object.data);
          break;
        default:
          bootbox.alert("Didn't understand the message type "+data_object.type);
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

    $(document).off('click',"#start-listening");
    $(document).on('click', '#start-listening', function(event) {
      event.preventDefault();
      message = send_settings_and_start_listening();
      ws.send(JSON.stringify(message));
    });

    $(document).off('click',"#stop-job");
    $(document).on('click', '#stop-job', function(event) {
      event.preventDefault();
      message = {"command": "kill_job", "data": "Kill this job!"};
      ws.send(JSON.stringify(message));
    });

    $(document).off('click',"#update-warp-directory");
    $(document).on('click', '#update-warp-directory', function(event) {
      bootbox.prompt({
        title: "Enter the full path for your new Warp directory.",
        closeButton: false,
        callback: function(result) {
          message = {"command": "change_directory", "data": result}
          ws.send(JSON.stringify(message));
        }
      });
                  // message = {"command": "change_directory", "data": $("#warp-directory").val()};
                  // console.log(message);
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
      ws.send(JSON.stringify({command: "get_gallery", data: {gallery_number: $(this).val()}
      }));
    });

    $(document).off('click',"[data-toggle='lightbox']");
    $(document).on('click', '[data-toggle="lightbox"]', function(event) {
                    event.preventDefault();
                    $(this).ekkoLightbox({
                      showArrows: false,
                      width: 300,
                      height: 300
                    });
    });
  }
  function prepare_settings() {
    data = {}
    data.mask_radius=$("#mask-radius").val();
    data.classification_type = $("input[name='classification-type']:checked").val();
    data.high_res_initial =$("#high-res-initial").val();
    data.high_res_final = $("#high-res-final").val();
    data.run_count_startup = $("#startup-cycle-count").val();
    data.run_count_refine = $("#refinement-cycle-count").val();
    data.particle_count_initial = $("#start-count").val();
    data.particle_count_update = $("#update-count").val();
    data.class_number = $("#number-classes").val();
    data.particles_per_class = $("#number-per-class").val();
    data.automask = $("#automask").prop("checked");
    data.autocenter = $("#autocenter").prop("checked");
    return data;
  }


  function get_settings_from_server(settings) {
    console.log("Updating Frontend Settings");
    console.log(settings);
    warp_folder_list = settings.warp_folder.split("/");
    warp_folder = warp_folder_list.pop();
    if (warp_folder == "") {
      warp_folder = warp_folder_list.pop();
    }

    $("#warp-directory").html(warp_folder);
    $("#neural-net").html(settings.settings.neural_net);
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
    $("#automask").prop("checked", settings.settings.automask).show();
    switch (settings.job_status) {
      case "running":
        $("#job-status").html("Running");
        $( "#update-warp-directory" ).prop( "disabled", true );
        $('#update-warp_directory').popover('hide');
        $( "#start-job" ).prop( "disabled", true );
        $('#start-job').popover('hide');
        $( "#start-listening" ).prop( "disabled", true );
        $('#start-listening').popover("hide");
        $( "#stop-job" ).prop( "disabled", false );
        disable_form();
        break;
      case "listening":
        $("#job-status").html("Waiting for New Particles");
        $( "#update-warp-directory" ).prop( "disabled", true );
        $( "#start-job" ).prop( "disabled", false );
        $( "#start-listening" ).prop( "disabled", true );
        $('#start-listening').popover("hide");
        $( "#stop-job" ).prop( "disabled", false );
        enable_form();
        // $('#stop-job').popover('hide');
        break;
      case "stopped":
        $("#job-status").html("Ready for New Runs");
        $( "#update-warp-directory" ).prop( "disabled", false );
        $("#update-warp-directory").popover("hide");
        $( "#start-job" ).prop( "disabled", false );
        $( "#start-listening" ).prop( "disabled", false );
        $( "#stop-job" ).prop( "disabled", true );
        $('#stop-job').popover('hide');
        enable_form();
        break;
      case "killed":
        $("#job-status").html("Waiting to Kill");
        $( "#update-warp-directory" ).prop( "disabled", true );
        $("#update-warp-directory").popover('hide');
        $( "#start-job" ).prop( "disabled", true );
        $('#start-job').popover('hide');
        $( "#start-listening" ).prop( "disabled", true );
        $('#start-listening').popover("hide");
        $( "#stop-job" ).prop( "disabled", true );
        $('#stop-job').popover('hide');
        disable_form();
        break;
      default:
        bootbox.alert("Something is wrong with the job-status setting: "+settings.job_status)

    }

    // bootbox.alert("settings: "+settings)
  }


  function disable_form () {
    console.log($('#subleft input'))
    $("#subleft input").each(function() {$(this).attr("disabled", true);});
    $("#subleft label").each(function() {$(this).attr("disabled", true);});
  }
  function enable_form() {
    console.log("#subleft input")
    $("#subleft input").each(function() {$(this).attr("disabled", false);});
    $("#subleft label").each(function() {$(this).attr("disabled", false);});
    $("input[name='classification-type']:checked").click()
  }
  function change_warp_directory(directory) {
    message = {command: "change_directory", data: directory};
    return message;
  }

  function send_settings_and_start_job() {
    message = {command: "start_job",
              data: prepare_settings()
    };
    return message;
  }

    function send_settings_and_start_listening() {
      message = {command: "listen",
                data: prepare_settings()
      }
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
  }
})

$(document).on('click', '#classification-type label', function(event) {
  var refinement_type_selected = $(this).children('input').attr("id");
  switch (refinement_type_selected) {
    case "abinit":
      $("#startup-cycle-count").attr("disabled", false);
      $("#high-res-initial").attr("disabled", false);
      $("#number-per-class").attr("disabled", false);
      $("#number-classes").attr("disabled", false);
      break;
    case "seeded":
      $("#startup-cycle-count").attr("disabled", false);
      $("#high-res-initial").attr("disabled", false);
      $("#number-per-class").attr("disabled", true);
      $("#number-classes").attr("disabled", true);
      break;
    case "refine":
      $("#startup-cycle-count").attr("disabled", true);
      $("#high-res-initial").attr("disabled", true);
      $("#number-per-class").attr("disabled", true);
      $("#number-classes").attr("disabled", true);
      break;
  }

});




function set_vars(uri_from_server){
  uri = uri_from_server;
}

//
// $(document).on('click', '[data-toggle="lightbox"]', function(event) {
//                 event.preventDefault();
//                 $(this).ekkoLightbox();
// });
