$(document).ready(function () {
    $.ajax({
        url: "http://services.googlecloud.fr:5001/promotions",
        type: 'GET'
    }).then(function (data) {
        $('.response').append(JSON.stringify(data));
    });
});