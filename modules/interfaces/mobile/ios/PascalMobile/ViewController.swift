import AVFoundation
import UIKit
import WebRTC

final class ViewController: UIViewController {
    private let serverUrl = URL(string: BuildConfig.serverURLString.trimmingCharacters(in: CharacterSet(charactersIn: "/")))
    private let httpSession = URLSession(configuration: .default)
    private let faceView = PascalFaceView()

    private var factory: RTCPeerConnectionFactory?
    private var peerConnection: RTCPeerConnection?
    private var cameraCapturer: RTCCameraVideoCapturer?
    private var didAutoStart = false
    private var didPostOffer = false

    override var supportedInterfaceOrientations: UIInterfaceOrientationMask {
        return .landscape
    }

    override var preferredInterfaceOrientationForPresentation: UIInterfaceOrientation {
        return .landscapeRight
    }

    override var prefersStatusBarHidden: Bool {
        return true
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        buildInterface()
        faceView.setMode(.connecting)
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        guard !didAutoStart else {
            return
        }
        didAutoStart = true
        start()
    }

    private func start() {
        guard let serverUrl = serverUrl else {
            faceView.setMode(.error)
            return
        }

        healthCheck(serverUrl: serverUrl) { [weak self] isHealthy in
            DispatchQueue.main.async {
                if isHealthy {
                    self?.requestPermissions()
                } else {
                    self?.faceView.setMode(.error)
                }
            }
        }
    }

    private func requestPermissions() {
        AVCaptureDevice.requestAccess(for: .video) { [weak self] cameraAllowed in
            AVCaptureDevice.requestAccess(for: .audio) { microphoneAllowed in
                DispatchQueue.main.async {
                    guard cameraAllowed, microphoneAllowed else {
                        self?.faceView.setMode(.error)
                        return
                    }
                    self?.startWebRTC()
                }
            }
        }
    }

    private func startWebRTC() {
        RTCPeerConnectionFactory.initialize()
        let encoderFactory = RTCDefaultVideoEncoderFactory()
        let decoderFactory = RTCDefaultVideoDecoderFactory()
        let factory = RTCPeerConnectionFactory(encoderFactory: encoderFactory, decoderFactory: decoderFactory)
        self.factory = factory

        let config = RTCConfiguration()
        config.sdpSemantics = .unifiedPlan
        config.iceServers = [RTCIceServer(urlStrings: ["stun:stun.l.google.com:19302"])]

        let constraints = RTCMediaConstraints(
            mandatoryConstraints: nil,
            optionalConstraints: ["DtlsSrtpKeyAgreement": "true"]
        )
        guard let peerConnection = factory.peerConnection(with: config, constraints: constraints, delegate: self) else {
            faceView.setMode(.error)
            return
        }
        self.peerConnection = peerConnection

        addLocalTracks(factory: factory, peerConnection: peerConnection)
        createOffer(peerConnection: peerConnection)
    }

    private func addLocalTracks(factory: RTCPeerConnectionFactory, peerConnection: RTCPeerConnection) {
        let audioTrack = factory.audioTrack(withTrackId: "pascal-audio")
        peerConnection.add(audioTrack, streamIds: ["pascal"])

        let videoSource = factory.videoSource()
        let capturer = RTCCameraVideoCapturer(delegate: videoSource)
        cameraCapturer = capturer
        let videoTrack = factory.videoTrack(with: videoSource, trackId: "pascal-video")
        peerConnection.add(videoTrack, streamIds: ["pascal"])
        startCamera(capturer: capturer)
    }

    private func startCamera(capturer: RTCCameraVideoCapturer) {
        guard let camera = RTCCameraVideoCapturer.captureDevices().first(where: { $0.position == .front }) ??
            RTCCameraVideoCapturer.captureDevices().first else {
            faceView.setMode(.error)
            return
        }

        let formats = RTCCameraVideoCapturer.supportedFormats(for: camera)
        let selectedFormat = formats.max { left, right in
            let leftDimensions = CMVideoFormatDescriptionGetDimensions(left.formatDescription)
            let rightDimensions = CMVideoFormatDescriptionGetDimensions(right.formatDescription)
            return leftDimensions.width < rightDimensions.width
        }
        guard let format = selectedFormat else {
            faceView.setMode(.error)
            return
        }

        let fps = min(format.videoSupportedFrameRateRanges.first?.maxFrameRate ?? 30, 30)
        capturer.startCapture(with: camera, format: format, fps: Int(fps)) { [weak self] error in
            DispatchQueue.main.async {
                self?.faceView.setMode(error == nil ? .watching : .error)
            }
        }
    }

    private func createOffer(peerConnection: RTCPeerConnection) {
        let constraints = RTCMediaConstraints(
            mandatoryConstraints: [
                "OfferToReceiveAudio": "false",
                "OfferToReceiveVideo": "false"
            ],
            optionalConstraints: nil
        )
        peerConnection.offer(for: constraints) { [weak self] description, error in
            guard let self = self, let description = description, error == nil else {
                DispatchQueue.main.async { self?.faceView.setMode(.error) }
                return
            }

            peerConnection.setLocalDescription(description) { [weak self] error in
                guard error == nil else {
                    DispatchQueue.main.async { self?.faceView.setMode(.error) }
                    return
                }
                DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                    self?.postLocalOfferIfReady()
                }
            }
        }
    }

    private func postLocalOfferIfReady() {
        guard !didPostOffer,
              let peerConnection = peerConnection,
              let description = peerConnection.localDescription else {
            return
        }
        didPostOffer = true

        let payload: [String: String] = [
            "sdp": description.sdp,
            "type": "offer"
        ]
        guard let body = try? JSONSerialization.data(withJSONObject: payload, options: []),
              var request = request(path: "/v1/webrtc/offer", method: "POST") else {
            faceView.setMode(.error)
            return
        }

        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = body
        httpSession.dataTask(with: request) { [weak self] data, response, error in
            guard let self = self,
                  error == nil,
                  let data = data,
                  let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode >= 200,
                  httpResponse.statusCode < 300,
                  let answer = try? JSONDecoder().decode(SessionDescription.self, from: data) else {
                DispatchQueue.main.async { self?.faceView.setMode(.error) }
                return
            }

            let remoteDescription = RTCSessionDescription(type: .answer, sdp: answer.sdp)
            peerConnection.setRemoteDescription(remoteDescription) { error in
                DispatchQueue.main.async {
                    self.faceView.setMode(error == nil ? .watching : .error)
                }
            }
        }.resume()
    }

    private func healthCheck(serverUrl: URL, completion: @escaping (Bool) -> Void) {
        guard let url = URL(string: "/health", relativeTo: serverUrl) else {
            completion(false)
            return
        }

        httpSession.dataTask(with: url) { _, response, error in
            if error != nil {
                completion(false)
                return
            }
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
            completion(statusCode >= 200 && statusCode < 300)
        }.resume()
    }

    private func request(path: String, method: String) -> URLRequest? {
        guard let serverUrl = serverUrl,
              let url = URL(string: path, relativeTo: serverUrl) else {
            return nil
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        return request
    }

    private func buildInterface() {
        view.backgroundColor = UIColor(red: 0.02, green: 0.03, blue: 0.05, alpha: 1)
        faceView.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(faceView)

        NSLayoutConstraint.activate([
            faceView.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            faceView.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor),
            faceView.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor),
            faceView.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor)
        ])
    }
}

extension ViewController: RTCPeerConnectionDelegate {
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange stateChanged: RTCSignalingState) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didAdd stream: RTCMediaStream) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didRemove stream: RTCMediaStream) {}
    func peerConnectionShouldNegotiate(_ peerConnection: RTCPeerConnection) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceConnectionState) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceGatheringState) {
        if newState == .complete {
            DispatchQueue.main.async { [weak self] in
                self?.postLocalOfferIfReady()
            }
        }
    }
    func peerConnection(_ peerConnection: RTCPeerConnection, didGenerate candidate: RTCIceCandidate) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didRemove candidates: [RTCIceCandidate]) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didOpen dataChannel: RTCDataChannel) {}
}

private struct SessionDescription: Decodable {
    let sdp: String
}

private final class PascalFaceView: UIView {
    enum Mode {
        case connecting
        case watching
        case error
    }

    private var mode: Mode = .connecting

    func setMode(_ mode: Mode) {
        self.mode = mode
        setNeedsDisplay()
    }

    override func draw(_ rect: CGRect) {
        guard let context = UIGraphicsGetCurrentContext() else {
            return
        }

        UIColor(red: 0.015, green: 0.025, blue: 0.045, alpha: 1).setFill()
        context.fill(rect)

        let faceRect = rect.insetBy(dx: rect.width * 0.08, dy: rect.height * 0.10)
        let facePath = UIBezierPath(roundedRect: faceRect, cornerRadius: min(faceRect.width, faceRect.height) * 0.16)
        UIColor(red: 0.06, green: 0.09, blue: 0.12, alpha: 1).setFill()
        facePath.fill()
        statusColor().setStroke()
        facePath.lineWidth = 5
        facePath.stroke()

        drawEye(center: CGPoint(x: faceRect.minX + faceRect.width * 0.32, y: faceRect.minY + faceRect.height * 0.38), in: faceRect)
        drawEye(center: CGPoint(x: faceRect.minX + faceRect.width * 0.68, y: faceRect.minY + faceRect.height * 0.38), in: faceRect)
        drawMouth(in: faceRect)
    }

    private func drawEye(center: CGPoint, in faceRect: CGRect) {
        let eyeWidth = faceRect.width * 0.16
        let eyeHeight = faceRect.height * 0.12
        let eyeRect = CGRect(
            x: center.x - eyeWidth / 2,
            y: center.y - eyeHeight / 2,
            width: eyeWidth,
            height: eyeHeight
        )
        let eyePath = UIBezierPath(roundedRect: eyeRect, cornerRadius: eyeHeight / 2)
        statusColor().setFill()
        eyePath.fill()
    }

    private func drawMouth(in faceRect: CGRect) {
        let mouthWidth = faceRect.width * 0.34
        let mouthHeight = faceRect.height * 0.045
        let mouthRect = CGRect(
            x: faceRect.midX - mouthWidth / 2,
            y: faceRect.minY + faceRect.height * 0.66 - mouthHeight / 2,
            width: mouthWidth,
            height: mouthHeight
        )
        let mouthPath = UIBezierPath(roundedRect: mouthRect, cornerRadius: mouthHeight / 2)
        statusColor().setFill()
        mouthPath.fill()
    }

    private func statusColor() -> UIColor {
        switch mode {
        case .connecting:
            return UIColor(red: 0.95, green: 0.78, blue: 0.30, alpha: 1)
        case .watching:
            return UIColor(red: 0.21, green: 0.80, blue: 0.72, alpha: 1)
        case .error:
            return UIColor(red: 1.0, green: 0.26, blue: 0.24, alpha: 1)
        }
    }
}
