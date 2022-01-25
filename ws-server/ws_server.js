const ws = require("ws");
const { createLndConnection } = require("./lnd_client");
const zmq = require("zeromq");

let lndConnecton = createLndConnection();
let invoiceHook = lndConnecton.subscribeInvoices({});
let sendPaymentHook = lndConnecton.sendPayment();

const AUTHENTICATION = "authentication";
const SEND_PAYMENT = "sendPayment";
const CREATE_INVOICE = "createInvoice";
const GET_CHANNEL_BALANCES = "getChannelBalances";
const GET_WALLET_BALANCES = "getWalletBalances";
const GET_NODE_INFO = "getNodeInfo";
const LNURL_AUTH = "lnurlAuth";

const ZMQ_ADDRESS = "tcp://127.0.0.1:5556";

const createResponse = (data, type) => {
  const resp = {
    type: type,
    data: data,
  };
  return JSON.stringify(resp);
};

async function zmqSubscriber(onMessage) {
  const subSocket = new zmq.Reply();

  await subSocket.connect("tcp://127.0.0.1:3002");

  for await (const [topic, msg] of subSocket) {
    onMessage(topic, msg);
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
    ws.send(msg.toString());
  };

  // zmqSubscriber(onZmqMessage).then(() =>{})

  invoiceHook.on("data", function (invoice) {
    if (invoice.settled) {
      const data = {
        amount: invoice.amt_paid_sat,
      };
      ws.send(createResponse(data, "receivedPayment"));

      lndConnecton.channelBalance({}, (err, response) => {
        if (err) {
          const data = {
            msg: "There was an error getting channel balancs.",
          };
          ws.send(createResponse(data, "error"));
        }
        ws.send(createResponse(response, "channelBalances"));
      });
    }
  });

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