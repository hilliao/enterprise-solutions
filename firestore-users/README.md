# Firestore sample code in Node js
The sample code follows the [Google Cloud firestore quickstart](https://cloud.google.com/firestore/docs/quickstart-servers)
 and [Firebase guides](https://firebase.google.com/docs/firestore/query-data/get-data) NODE.JS example.
 
 ## Configure the project ID and service account key file path in each file
 ```javascript
 const db = new Firestore({
     projectId: 'car-repair-warranty',
     keyFilename: '/home/hil/secrets/firestore-user-200113140848.json'
 });
 ```
 
 ## reference links
 https://firebase.google.com/docs/firestore/query-data/queries