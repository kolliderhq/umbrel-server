# Umbrel Server

## Backend

```
cp sample.config.json config.json
pip install -r requirements.txt
python main.py
```
**Note**: Make sure the right config variables are set. If you don't set the variables for the Kollider API then it will not hedge.


## Ws Server

```
cp sample.config.json config.json
npm install
node ws_server.js
```

**Note**: Same here, make sure the config variables are set correctly.