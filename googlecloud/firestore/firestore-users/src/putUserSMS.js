/*
 * Firestore sample of putting documents
 */

const Firestore = require('@google-cloud/firestore');

const db = new Firestore({
    projectId: 'car-repair-warranty',
    keyFilename: '/home/hil/secrets/firestore-user-200113140848.json'
});

const usersCol = 'users';
const testUsers = ['630-272-9749', '630-272-9748', '630-272-9747'];

function putSMSUser(db, user, response) {
    let userDoc = db.collection(usersCol).doc(user);

    let op = userDoc.set({
        'response': response
    });

    return op;
}


function getAllSMS(db, callback) {

    let userCol = db.collection(usersCol).get().then(function (snapshot) {
        var array = [];

        snapshot.forEach(user => {
            array.push(user.id);
        });

        callback(array);
    });
}

// create or update SMS users
testUsers.forEach(user => {
    putSMSUser(db, user, Math.round(Math.random() * 2)).then(function (result) {
        process.stdout.write(`user ${user} operation: `);
        console.log(result)
    });
});

// get all SMS user IDs in an array
getAllSMS(db, function (array) {
    console.log('all SMS numbers: ' + array)
});
