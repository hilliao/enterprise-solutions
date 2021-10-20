$(document).ready(function () {
    const urlParams = new URLSearchParams(window.location.search);
    const queryParam = urlParams.get('promo-code');

    $('#promo').val(queryParam);
});

$(document).ready(function () {
    $('#submit').click(function () {
        console.log("clicked redeem");
        var promo = $('#promo').val();
        var email = $('#email').val();
        var name = $('#name').val();

        $.ajax({
            url: 'http://services.googlecloud.fr:5001/promotions/' + promo,
            method: 'PUT',
            "headers": {
                "Content-Type": "application/json"
            },
            data: JSON.stringify({
                email: email,
                name: name,
            }),
            error: function (jqXHR, exception) {
                document.getElementById("put_response").innerHTML +=
                    '<p style="color:red;">' + JSON.stringify(jqXHR) + '</p>'
            }
        }).then(function (put_res) {
            var google_form = "Please proceed to submit <a href=" + put_res['form-url'] + ">the Google form</a> to complete the process"
            document.getElementById("put_response").innerHTML +=
                '<p style="color:green;">' + JSON.stringify(put_res) + '<br>' + google_form + '</p>'

            $('.put_response').append(JSON.stringify(put_res));
            $('.put_response').append();
            $('.put_response').css("color", "green");
        });
    });
});