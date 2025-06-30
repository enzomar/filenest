function fileNestApp() {
  return {
    apiKey: '',
    buckets: [],
    selectedBucket: null,
    records: [],
    selectedRecord: null,
    imageInfo: '',
    authenticated: false,
    darkMode: localStorage.getItem('darkMode') === 'true',
    jsonEditor: null,
    fileSize: '',
    textPreview: '',

    init() {
      if (this.darkMode) {
        document.body.classList.add('dark-mode');
      }

      this.$watch('selectedRecord', (file) => {
        if (this.jsonEditor) {
          this.jsonEditor.destroy();
          this.jsonEditor = null;
        }

        if (file && document.getElementById('jsoneditor')) {
          this.jsonEditor = new JSONEditor(document.getElementById('jsoneditor'), {
            mode: 'tree',
            modes: ['code', 'form', 'text', 'tree', 'view'],
            onError: (err) => alert(err.toString()),
          });
          this.jsonEditor.set(file.metadata || {});
        }
      });
    },

    toggleDarkMode() {
      this.darkMode = !this.darkMode;
      localStorage.setItem('darkMode', this.darkMode);
      document.body.classList.toggle('dark-mode', this.darkMode);
    },

 // NEW helper to append api-key param safely
    getAuthenticatedFileUrl(url) {
      if (!url) return url;
      const separator = url.includes('?') ? '&' : '?';
      return `${url}${separator}api-key=${encodeURIComponent(this.apiKey)}`;
    },


    loadBuckets() {
      fetch('/api/v1/buckets', {
        headers: { 'x-api-key': this.apiKey }
      })
        .then(res => {
          if (!res.ok) throw new Error('Invalid API key or unable to fetch buckets');
          return res.json();
        })
        .then(data => {
          this.buckets = data.buckets || [];
          this.authenticated = true;
          this.selectedBucket = null;
          this.records = [];
          this.selectedRecord = null;
        })
        .catch(err => alert(err.message));
    },

    loadRecords(bucket) {
      this.selectedBucket = bucket;
      fetch(`/api/v1/buckets/${bucket}/records`, {
        headers: { 'x-api-key': this.apiKey }
      })
        .then(res => {
          if (!res.ok) throw new Error('Failed to load records');
          return res.json();
        })
        .then(data => {
          this.records = Array.isArray(data) ? data : [];
          this.selectedRecord = null;
          this.imageInfo = '';
        })
        .catch(err => alert(err.message));
    },

async loadRecord(bucket, record_id) {
      this.selectedBucket = bucket;
      this.imageInfo = '';
      this.fileSize = ''; // reset on new load
      try {
        const res = await fetch(`/api/v1/buckets/${bucket}/records/${record_id}`, {
          headers: { 'x-api-key': this.apiKey }
        });
        if (!res.ok) throw new Error('Failed to load record');
        const data = await res.json();
        this.selectedRecord = data;


        // Use authenticated URL here:
        const authFileUrl = this.getAuthenticatedFileUrl(data.file_url);
        const fileUrl = data.file_url;
        this.selectedRecord.auth_file_url = authFileUrl;

        // Fetch file size using HEAD request if file_url exists
        if (authFileUrl) {
          try {
            const headResp = await fetch(authFileUrl, { method: 'HEAD' });
            if (headResp.ok) {
              const len = headResp.headers.get('content-length');
              if (len) {
                this.fileSize = this.formatFileSize(parseInt(len, 10));
              } else {
                this.fileSize = 'Unknown size';
              }
            }
          } catch {
            this.fileSize = 'Unknown size';
          }
        }

        // Fetch text preview if text file
if (this.selectedRecordIsText()) {
  try {
    const resp = await fetch(authFileUrl, {
      headers: { 'x-api-key': this.apiKey },
      method: 'GET',
    });
    if (resp.ok) {
      const text = await resp.text();
      this.textPreview = text.slice(0, 300);
    } else {
      this.textPreview = "Could not load preview.";
    }
  } catch (e) {
    this.textPreview = "Error loading preview.";
  }
} else {
  this.textPreview = '';  // Clear if not text file
}

        // Image preview info (if image)
        if (fileUrl?.match(/\.(jpg|jpeg|png|gif|bmp|webp)$/i)) {
          const img = new Image();
          img.onload = () => {
            this.imageInfo = `Dimensions: ${img.naturalWidth}x${img.naturalHeight}px`;
            if (this.fileSize) this.imageInfo += ` | Size: ${this.fileSize}`;
          };
          img.src = authFileUrl;
        }
      } catch (err) {
        alert(err.message);
      }
    },


    async updateMetadata() {
      if (!this.selectedRecord || !this.selectedBucket || !this.jsonEditor) {
        alert("No file selected or JSON editor missing");
        return;
      }

      let metadata;
      try {
        metadata = this.jsonEditor.get();
      } catch (e) {
        alert("Invalid JSON format");
        return;
      }

      const url = `/api/v1/buckets/${this.selectedBucket}/records/${this.selectedRecord.id}/metadata`;

      try {
        const res = await fetch(url, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            "x-api-key": this.apiKey
          },
          body: JSON.stringify(metadata)
        });

        if (!res.ok) {
          const error = await res.json().catch(() => ({}));
          throw new Error(error.detail || res.statusText);
        }

        alert("Metadata updated!");
        this.selectedRecord.metadata = metadata;

      } catch (err) {
        alert("Failed to update metadata: " + err.message);
      }
    },

    async deleteBucket(bucket) {
      if (!confirm(`Are you sure you want to delete the bucket "${bucket}"? This action cannot be undone.`)) {
        return;
      }
      try {
        const res = await fetch(`/api/v1/buckets/${bucket}`, {
          method: 'DELETE',
          headers: { 'x-api-key': this.apiKey }
        });
        if (!res.ok) {
          const error = await res.json().catch(() => ({}));
          throw new Error(error.detail || 'Failed to delete bucket');
        }
        alert(`Bucket "${bucket}" deleted.`);
        // Reload buckets and clear selection if necessary
        this.loadBuckets();
        if (this.selectedBucket === bucket) {
          this.selectedBucket = null;
          this.records = [];
          this.selectedRecord = null;
        }
      } catch (err) {
        alert('Error deleting bucket: ' + err.message);
      }
    },

    async deleteFile(bucket, record_id) {
      if (!confirm('Are you sure you want to delete this file? This action cannot be undone.')) {
        return;
      }
      try {
        const res = await fetch(`/api/v1/buckets/${bucket}/records/${record_id}`, {
          method: 'DELETE',
          headers: { 'x-api-key': this.apiKey }
        });
        if (!res.ok) {
          const error = await res.json().catch(() => ({}));
          throw new Error(error.detail || 'Failed to delete file');
        }
        alert('File deleted.');
        // Reload records list and clear selection if needed
        this.loadRecords(bucket);
        if (this.selectedRecord && this.selectedRecord.id === record_id) {
          this.selectedRecord = null;
          this.imageInfo = '';
        }
      } catch (err) {
        alert('Error deleting file: ' + err.message);
      }
    },

    get selectedRecordIsImage() {
      return this.selectedRecord?.file_url?.match(/\.(jpg|jpeg|png|gif|bmp|webp)$/i);
    },

    formatDate(dateStr) {
  if (!dateStr) return 'N/A';
  try {
    const dt = new Date(dateStr);
    return dt.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  } catch {
    return dateStr;
  }
},
formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
},

copyToClipboard(text) {
  if (!text) return;
  navigator.clipboard.writeText(text)
    .then(() => {
      alert("Copied to clipboard!");
    })
    .catch(err => {
      console.error("Copy failed:", err);
      alert("Failed to copy link");
    });
},
selectedRecordIsText() {
  return this.selectedRecord?.file_url?.match(/\.(txt|md|json|csv|log|xml|yaml|yml)$/i);
},

  };
}
