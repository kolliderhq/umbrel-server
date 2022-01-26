const ws = require("ws");
const zmq = require("zeromq");

const AUTHENTICATION = "authentication";
const SEND_PAYMENT = "sendPayment";
const CREATE_INVOICE = "createInvoice";
const GET_CHANNEL_BALANCES = "getChannelBalances";
const GET_WALLET_BALANCES = "getWalletBalances";
const GET_NODE_INFO = "getNodeInfo";
const LNURL_AUTH = "lnurlAuth";

const ZMQ_ADDRESS = "tcp://127.0.0.1:5556";
const ZMQ_SUB_ADDRESS = "tcp://127.0.0.1:5557"

const createResponse = (data, type) => {
  const resp = {
    type: type,
    data: data,
  };
  return JSON.stringify(resp);
};

async function zmqSubscriber(onMessage) {
  const subSocket = new zmq.Subscriber();

  await subSocket.connect(ZMQ_SUB_ADDRESS);
  subSocket.subscribe("invoices")

  for await (const [topic, msg] of subSocket) {
    onMessage(msg);
  }
}

async function zmqRequest(msg, onReply) {
  const socket = new zmq.Request();
  socket.connect(ZMQ_ADDRESS);
  await socket.send(msg);
  const [result] = await socket.receive();
  console.log(result);
  onReply(result);
}

const wss = new ws.WebSocketServer({
  port: 8080,
  perMessageDeflate: false,
});

wss.on("connection", function connection(ws) {
  let isAuthenticated = false;

  const onZmqReply = (msg) => {
    console.log(msg)
    ws.send(msg.toString());
  };

  zmqSubscriber(onZmqReply)

  ws.on("message", function message(data) {
    let d = "";
    try {
      d = JSON.parse(data);
    } catch (err) {
      return null;
    }
    if (d.type === CREATE_INVOICE) {
      let amount = d.amount;
      if (!amount) {
        ws.send(createResponse({ msg: "Amount not specified" }, "error"));
      } else {
        const msg = {
          action: "create_invoice",
          data: {
            amount: d.amount,
          },
        };
        zmqRequest(JSON.stringify(msg), onZmqReply);
      }
    } else if (d.type === SEND_PAYMENT) {
      if (!d.paymentRequest) {
        const data = {
          msg: "Payment request not provided.",
        };
        ws.send(createResponse(data, "error"));
      } else {
        const msg = {
          action: "send_payment",
          data: {
            payment_request: d.paymentRequest,
          },
        };
        zmqRequest(JSON.stringify(msg), onZmqReply);
      }
    } else if (d.type === GET_NODE_INFO) {
      const msg = {
        action: "get_node_info",
      };
      zmqRequest(JSON.stringify(msg), onZmqReply);
    } else if (d.type === GET_CHANNEL_BALANCES) {
      const msg = {
        action: "get_channel_balances",
      };
      zmqRequest(JSON.stringify(msg), onZmqReply);
    } else if (d.type === GET_WALLET_BALANCES) {
      const msg = {
        action: "get_wallet_balances",
      };
      zmqRequest(JSON.stringify(msg), onZmqReply);
    } else if (d.type === LNURL_AUTH) {
      const msg = {
        action: "lnurl_auth",
        data: { lnurl: d.lnurl },
      };
      zmqRequest(JSON.stringify(msg), onZmqReply);
    } else if (d.type === AUTHENTICATION) {
      let env_password = process.env.APP_PASSWORD;
      if (d.password === env_password) {
        const data = {
          status: "success",
        };
        isAuthenticated = true;
        ws.send(createResponse(data, "authentication"));
      } else {
        const data = {
          msg: "wrong password",
        };
        ws.send(createResponse(data, "authentication"));
      }
    } else {
      ws.send(createResponse({ msg: "Action does not exist" }, "error"));
    }
  });
});
