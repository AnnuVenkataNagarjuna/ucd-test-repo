const express = require('express');
const path = require('path');
const app = express();

// Use PORT from environment or default to 3000
const PORT = process.env.PORT || 3000;
const ENV = process.env.NODE_ENV || 'production';

// Serve static assets from public folder
app.use(express.static(path.join(__name, 'public')));

// Simple API endpoint to return status
app.get('/api/status', (req, res) => {
    res.json({
        status: 'UP',
        environment: ENV,
        port: PORT,
        timestamp: new Date().toISOString(),
        version: '1.0.0'
    });
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`UCD Test Application running on port ${PORT} in ${ENV} mode`);
});
