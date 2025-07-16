
document.addEventListener("DOMContentLoaded", () => {
  const socket = io();
  const msgInput = document.getElementById("msgInput");
  const messages = document.getElementById("messages");
  const systemMessages = document.getElementById("systemMessages");
  const historyView = document.getElementById("historyView");
  
  

  // Send message
  function sendMessage() {
    const msg = msgInput.value;
    if (msg) {
      socket.emit("send_message", { msg, sender: displayName });
      msgInput.value = "";
    }
  }

  // Request chat history from server
  function getHistory() {
    socket.emit("get_history");
  }

 function viewUploadedFiles() {
  const links = Array.from(document.querySelectorAll("#messages a"))
    .filter(a => a.href.includes("/uploads/"))
    .map(a => `<li><a href="${a.href}" target="_blank">${a.textContent}</a></li>`);

  if (!links.length) {
    alert("No uploaded files yet.");
    return;
  }

  const panel = document.getElementById("uploadedFilesPanel");
  const list = document.getElementById("uploadedFileList");
  list.innerHTML = links.join("");
  panel.style.display = "block";
  }

 function closeFilesPanel() {
  document.getElementById("uploadedFilesPanel").style.display = "none";
}


  // Clear chat history (from backend)
 function clearHistory() {
  fetch("/clear_history", {
    method: "POST",
  })
    .then((res) => res.json())
    .then((result) => {
      if (result.success) {
        closeHistoryView(); // hide history after clearing
      }
    });
 }


  // Switch between public and private modes
  function switchMode() {
    const currentMode = document.getElementById("modeStatus").innerText;
    const isPrivate = currentMode.includes("Private");

    if (isPrivate) {
      socket.emit("switch_public");
      document.getElementById("modeStatus").innerText = "Mode: Public";
      messages.innerHTML = "";
    } else {
      const partner = prompt("Enter display name to chat with:");
      if (partner) {
        socket.emit("switch_private", { partner });
        document.getElementById("modeStatus").innerText = `Mode: Private → ${partner}`;
        messages.innerHTML = "";
      }
    }
  }

  // Back button logic
  function goBack() {
    const modeText = document.getElementById("modeStatus").innerText;
    if (modeText.includes("Private")) {
      socket.emit("switch_public");
      document.getElementById("modeStatus").innerText = "Mode: Public";
      messages.innerHTML = "";
    } else {
      window.location.href = "/login";
    }
  }

  // Hide history view
  function closeHistoryView() {
    historyView.style.display = "none";
    historyView.innerHTML = "";
  }

  // Send message with Enter key
 msgInput.addEventListener("keydown", function (event) {
  if (event.key === "Enter") {
    sendMessage();
  } else if (msgInput.value.length === 0 && event.key.length === 1 && !event.ctrlKey && !event.metaKey) {
    // Auto-capitalize first character
    const capital = event.key.toUpperCase();
    msgInput.value = capital;
    event.preventDefault();
  }
 });
 

  // Normal message handler
  socket.on("receive_message", (data) => {
    const div = document.createElement("div");
    div.className = data.sender === displayName ? "bubble right" : "bubble left";
    div.innerHTML = `<strong>${data.sender}</strong><br>${data.msg}`;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
  });

  // System message handler
  socket.on("system_message", (data) => {
    const sys = document.createElement("div");
    sys.innerText = data.msg;
    systemMessages.appendChild(sys);
    systemMessages.scrollTop = systemMessages.scrollHeight;
  });

  // Show chat history in new box
  socket.on("history", (data) => {
    historyView.style.display = "block";
    historyView.innerHTML = `
      <div style="text-align:right">
        <button onclick="closeHistoryView()">❌</button>
      </div>
      <h4>Chat History</h4>
    `;
    data.messages.forEach((line) => {
      const div = document.createElement("div");
      div.className = "bubble history";
      div.innerText = line;
      historyView.appendChild(div);
    });

    const clearBtn = document.createElement("button");
    clearBtn.innerText = "🧹 Clear History";
    clearBtn.onclick = clearHistory;
    historyView.appendChild(clearBtn);
  });

  // Handle private chat invitation
  socket.on("private_invite", (data) => {
    const accept = confirm(`🔐 Private chat request from ${data.from}. Accept?`);
    if (accept) {
      socket.emit("accept_private", { from: data.from });
      document.getElementById("modeStatus").innerText = `Mode: Private → ${data.from}`;
      messages.innerHTML = "";

      const sys = document.createElement("div");
      sys.innerText = `✅ You are now in private chat with ${data.from}`;
      systemMessages.appendChild(sys);
    } else {
      socket.emit("decline_private", { from: data.from });
    }
  });

  // Private message alert popup
  socket.on("private_message_alert", (data) => {
    const popup = document.createElement("div");
    popup.className = "private-popup";
    popup.innerText = `📨 You received a private message from ${data.from}`;
    document.body.appendChild(popup);
    setTimeout(() => {
      popup.remove();
    }, 4000);
  });

  // File upload
  document.getElementById("fileInput").addEventListener("change", async function () {
    const file = this.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch("/upload", {
      method: "POST",
      body: formData,
    });

    const result = await res.json();
    if (result.success) {
      const fileMsg = `📁 <a href="${result.url}" download target="_blank">${file.name}</a>`;
      socket.emit("send_message", {
        msg: fileMsg,
        sender: displayName,
      });
    } else {
      alert("❌ Failed to upload file.");
    }
  });

  // Handle private message switch prompt (user is still in public)
  socket.on("private_message_switch_prompt", (data) => {
  const promptPopup = document.createElement("div");
  promptPopup.className = "private-popup";
  promptPopup.innerHTML = `📨 <strong>${data.from}</strong> sent you a private message.<br><u>Click to open</u>`;
  promptPopup.style.cursor = "pointer";

  promptPopup.onclick = () => {
    socket.emit("switch_private", { partner: data.from });
    document.getElementById("modeStatus").innerText = `Mode: Private → ${data.from}`;
    messages.innerHTML = "";

    const sys = document.createElement("div");
    sys.innerText = `🔐 Switched to private chat with ${data.from}`;
    systemMessages.appendChild(sys);
  };

  document.body.appendChild(promptPopup);
  setTimeout(() => promptPopup.remove(), 8000); // Auto-hide after 8 sec
});


  // Bind functions to global scope
  window.sendMessage = sendMessage;
  window.getHistory = getHistory;
  window.switchMode = switchMode;
  window.goBack = goBack;
  window.closeHistoryView = closeHistoryView;
  window.viewUploadedFiles = viewUploadedFiles;
  window.closeFilesPanel = closeFilesPanel;


  // Join room
  socket.emit("join_chat", { display_name: displayName });
});


