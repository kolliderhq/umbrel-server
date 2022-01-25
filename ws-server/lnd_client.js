const fs = require("fs");
const grpc = require("@grpc/grpc-js");
const protoLoader = require("@grpc/proto-loader");

const config = require("./config.json")

const loaderOptions = {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
};

const createLndConnection = () => {

  const packageDefinition = protoLoader.loadSync(
    "lightning.proto",
    loaderOptions
  );

  process.env.GRPC_SSL_CIPHER_SUITES = "HIGH+ECDSA";

  // Lnd admin macaroon is at ~/.lnd/data/chain/bitcoin/simnet/admin.macaroon on Linux and
  // ~/Library/Application Support/Lnd/data/chain/bitcoin/simnet/admin.macaroon on Mac
  let m = fs.readFileSync(config.macaroon_path);
  let macaroon = m.toString("hex");

  // build meta data credentials
  let metadata = new grpc.Metadata();
  metadata.add("macaroon", macaroon);
  let macaroonCreds = grpc.credentials.createFromMetadataGenerator(
    (_args, callback) => {
      callback(null, metadata);
    }
  );

  // build ssl credentials using the cert the same as before
  let lndCert = fs.readFileSync(config.tls_path);
  let sslCreds = grpc.credentials.createSsl(lndCert);

  // combine the cert credentials and the macaroon auth credentials
  // such that every call is properly encrypted and authenticated
  let credentials = grpc.credentials.combineChannelCredentials(
    sslCreds,
    macaroonCreds
  );

  // Pass the crendentials when creating a channel
  let lnrpcDescriptor = grpc.loadPackageDefinition(packageDefinition);
  let lnrpc = lnrpcDescriptor.lnrpc;

  return new lnrpc.Lightning(`${config.node_url}:${config.node_port}`, credentials);

};

exports.createLndConnection = createLndConnection;