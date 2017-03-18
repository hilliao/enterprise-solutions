jQuery(function($) {
	$('body').addClass('postload');

	$(document).ready(function() {
    
		// Mobile menu
		$(".hamburger").click(function(){
			$("body").toggleClass("menu-open");
		});
		
		// Delay for iframe editor
    setTimeout(function() {
      $('body:not(.wsite-native-mobile-editor) #header').waypoint('sticky');
      $(".page-sidebar").css({ "padding-top" : $("#header").outerHeight() + "px"});
    }, 500);
    

    $('.wsite-mobile-menu').css({'padding-bottom' : $('.sticky-wrapper').height() +'px'});
    
    // Define Theme specific functions
    var Theme = {
      // Swiping mobile galleries wwith Hammer.js
      swipeGallery: function() {
        setTimeout(function() {
          var touchGallery = document.getElementsByClassName("fancybox-wrap")[0];
          var mc = new Hammer(touchGallery);
          mc.on("panleft panright", function(ev) {
            if (ev.type == "panleft") {
              $("a.fancybox-next").trigger("click");
            } else if (ev.type == "panright") {
              $("a.fancybox-prev").trigger("click");
            }
            Theme.swipeGallery();
          });
        }, 500);
      },
      swipeInit: function() {
        if ('ontouchstart' in window) {
          $("body").on("click", "a.w-fancybox", function() {
            Theme.swipeGallery();
          });
        }
      },
      interval: function(condition, action, duration, limit) {
        var counter = 0;
        var looper = setInterval(function(){
          if (counter >= limit || Theme.checkElement(condition)) {
            clearInterval(looper);
          } else {
            action();
            counter++;
          }
        }, duration);
      },
      checkElement: function(selector) {
        return $(selector).length;
      },
      moveCartLink: function() {
        if ($("#wsite-nav-cart-num").text().length && $("#wsite-nav-cart-num").text() != "-") {
          var cart = $(".wsite-nav-cart").detach();
          $("#search").after(cart).css({ 'padding-right': '75px'});
        }
      },
      moveLogin: function() {
        var login = $('#member-login').detach();
        $("#nav .wsite-menu-default li:last-child").after(login);
      }
    }
    
    Theme.interval("#header .container > .wsite-nav-cart", Theme.moveCartLink, 800, 5);
    Theme.interval("#nav #member-login", Theme.moveLogin, 800, 5);
    
    //
    // Old Superset Scripts
    //
		
		// Reveal search field
		$('#search .wsite-search-button').click(function(){
			$("#search").toggleClass("showsearch");
			if ($("#search").hasClass("showsearch")) {
					$("#search .wsite-search-input").focus();                
			}
			return false;
		});

		// click on body to close nav
		$('.page-content').on('click', function() {
		  $('#nav-trigger').prop('checked', false);
		});

    // Store category list click
    $('.wsite-com-sidebar').click(function() {
      if (!$(this).hasClass('sidebar-expanded')) {
        $(this).addClass('sidebar-expanded');
        if ($('#close').length === 0) {
          $("#wsite-com-hierarchy").prepend('<a id="close" href="#">CLOSE</a>');
          $('#close').click(function(e) {
            e.preventDefault();
            setTimeout(function() {
              $('.wsite-com-sidebar').removeClass('sidebar-expanded');
            }, 50);
          });
        }
      }
    });
    

	});

});