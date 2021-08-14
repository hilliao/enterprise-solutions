$(document).ready(function () {
    $.ajax({
        url: "http://services.googlecloud.fr:5001/promotions",
        type: 'GET'
    }).then(function (data) {
        $('.response').append(JSON.stringify(data));
    });
});

$(document).ready(function () {
    $('#submit').click(function () {
        console.log("click");
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
            })
        }).then(function (put_res) {
            $('.put_response').append(JSON.stringify(put_res));
        });
        ;

    });
});