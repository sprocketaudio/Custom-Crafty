function generateTotpQrCode(secret, user, issuer) {
    // Construct the TOTP URL
    const otpAuthUrl = `otpauth://totp/Crafty?secret=`;

    // Generate the QR code
    $('#qrcode').empty(); // Clear any existing QR code
    new QRCode(document.getElementById('qrcode'), {
        text: otpAuthUrl,
        width: 200, // Adjust size
        height: 200,
        colorDark: "#000000",
        colorLight: "#ffffff",
        correctLevel: QRCode.CorrectLevel.H
    });
}