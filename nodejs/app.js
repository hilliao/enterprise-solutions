var express = require('express');
var app = express();
var port = process.env.PORT || 3000;
app.get('/', function (req, res) {
    res.send('welcome to node js API');
});
var server = app.listen(port, function () {
    console.log('running on port: ' + port);
});