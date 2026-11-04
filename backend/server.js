 
require('dotenv').config();

const mongoose = require('mongoose');
const connectDB = require('./config/db');

const startServer = async () => {
  try {
    await connectDB();

    const db = mongoose.connection.db;

    const collections = await db.listCollections({
      name: 'users'
    }).toArray();

    if (collections.length === 0) {
      await db.createCollection('users');
      console.log('Users collection created successfully!');
    } else {
      console.log('Users collection already exists!');
    }

    await mongoose.disconnect();
    console.log('Database test completed.');
  } catch (error) {
    console.error(error.message);
    process.exit(1);
  }
};

startServer();
