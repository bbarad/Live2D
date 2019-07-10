



// Display Utilities go below here - just random stuff to make pretty things happen.
$(document).ready(function () {
  $('[rel="popover"]').popover(
    {container: 'body'}
  )
})


$(document).ready(function () {
  $('[rel="tooltip"]').tooltip(
    {container: 'body'}
  )
})


$(document).on('click', '[data-toggle="lightbox"]', function(event) {
                event.preventDefault();
                $(this).ekkoLightbox();
});
