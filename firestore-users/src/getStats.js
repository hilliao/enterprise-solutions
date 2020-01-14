/*
 * Firestore sample of getting documents
 */

const Firestore = require('@google-cloud/firestore');
const usersCol = 'users';

const db = new Firestore({
    projectId: 'car-repair-warranty',
    keyFilename: '/home/hil/secrets/firestore-user-200113140848.json'
});

function getSMSResRate(db, value, callback) {

    let userCol = db.collection(usersCol).where('response', '==', value)
        .get()
        .then(function (snapshot) {
            var valueCount = snapshot.size;
            let col = db.collection(usersCol)
                .get()
                .then(snapshot => {
                    var ColCount = snapshot.size;
                    callback(valueCount, ColCount);
                });
        });
}

const value = 1;
getSMSResRate(db, value, function (valueCount, collectionCount) {
    console.log(`count of ${value} : ` + valueCount)
    console.log(`collection count: ` + collectionCount)
    console.log('ratio: ' + valueCount / collectionCount)
});
