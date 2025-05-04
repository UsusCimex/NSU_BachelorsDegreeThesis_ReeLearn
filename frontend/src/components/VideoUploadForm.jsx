// src/components/VideoUploadForm.jsx
import React, { useState, useEffect, useRef } from "react";
import {
  Box,
  TextField,
  Button,
  LinearProgress,
  Typography,
  Paper,
  Snackbar,
  Alert,
  Grid,
  Tooltip,
  IconButton,
  Chip,
  Divider
} from "@mui/material";
import AlertMessage from "./AlertMessage";
import { uploadVideo, getTaskStatus } from "../services/api";
import { useTranslation } from "../hooks/useTranslation";
import StorageIcon from '@mui/icons-material/Storage';
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep';
import CheckIcon from '@mui/icons-material/Check';
import ErrorIcon from '@mui/icons-material/Error';
import WarningIcon from '@mui/icons-material/Warning';
import { formatFileSize } from "../utils/formatters";

const VideoUploadForm = () => {
  const [file, setFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [taskId, setTaskId] = useState("");
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState("");
  const [error, setError] = useState("");
  const [uploadWarning, setUploadWarning] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  
  const { t } = useTranslation();
  const fileInputRef = useRef();
  const uploadInProgress = useRef(false);

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file) {
      setError(t("pleaseSelectFile", "Please select a video file."));
      return;
    }
    
    // Проверка размера файла перед загрузкой
    if (file.size > 15 * 1024 * 1024 * 1024) { // 15 ГБ
      setError(t("fileTooLarge", "File size exceeds the maximum allowed (15 GB)."));
      return;
    }
    
    try {
      if (uploadInProgress.current) {
        setUploadWarning(t("uploadInProgress", "Upload already in progress, please wait."));
        return;
      }
      
      uploadInProgress.current = true;
      setStatusText(t("startingUpload", "Starting upload..."));
      setProgress(0);
      setUploadProgress(0);
      
      const res = await uploadVideo(file, name, description, (progressEvent) => {
        // Обработка прогресса загрузки
        const percentCompleted = Math.round(
          (progressEvent.loaded * 100) / progressEvent.total
        );
        setUploadProgress(percentCompleted);
        setStatusText(t("uploadingProgress", `Uploading: ${percentCompleted}%`));
      });
      setTaskId(res.task_id);
      setStatusText(t("processingVideo", "Processing video..."));
    } catch (err) {
      console.error("Upload error:", err);
      uploadInProgress.current = false;
      
      // Обработка специфичных ошибок
      if (err.response?.status === 507) {
        setError(t("noSpaceLeft", "Server disk space is full. Please try again later or contact administrator."));
      } else if (err.response?.status === 413) {
        setError(t("fileTooLarge", "File size is too large for server to process."));
      } else {
        setError(err.response?.data?.detail || err.message || t("uploadFailed", "Upload failed."));
      }
    }
  };

  useEffect(() => {
    let interval;
    if (taskId) {
      interval = setInterval(async () => {
        try {
          const statusRes = await getTaskStatus(taskId);
          setProgress(statusRes.progress || 0);
          setStatusText(statusRes.current_operation || "");
          
          if (statusRes.status === "completed") {
            clearInterval(interval);
            uploadInProgress.current = false;
          } else if (statusRes.status === "failed") {
            clearInterval(interval);
            uploadInProgress.current = false;
            setError(`${t("processingFailed", "Processing failed")}: ${statusRes.error || ''}`);
          }
        } catch (err) {
          console.error("Status check error:", err);
          clearInterval(interval);
          uploadInProgress.current = false;
          setError(err.response?.data?.detail || err.message || t("statusCheckFailed", "Failed to check upload status."));
        }
      }, 2000); // Проверка каждые 2 секунды
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [taskId, t]);

  const handleFileChange = (e) => {
    if (e.target.files.length > 0) {
      const selectedFile = e.target.files[0];
      setFile(selectedFile);
      
      // Отображаем предупреждение, если файл большой
      if (selectedFile.size > 1024 * 1024 * 1024) { // Более 1 ГБ
        setUploadWarning(
          t("largeFileWarning", "You're uploading a large file. It might take a while to process.")
        );
      } else {
        setUploadWarning("");
      }
    }
  };

  // Обработчики для drag & drop
  const handleDragOver = (e) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setDragOver(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const droppedFile = e.dataTransfer.files[0];
      setFile(droppedFile);
      
      // Отображаем предупреждение, если файл большой
      if (droppedFile.size > 1024 * 1024 * 1024) { // Более 1 ГБ
        setUploadWarning(
          t("largeFileWarning", "You're uploading a large file. It might take a while to process.")
        );
      } else {
        setUploadWarning("");
      }
      
      e.dataTransfer.clearData();
    }
  };

  return (
    <Box>
      <Divider sx={{ mb: 3 }} />
      
      <Box
        component="form"
        onSubmit={handleUpload}
        sx={{
          display: "flex",
          flexDirection: "column",
          gap: 2
        }}
      >
        {/* Область drag & drop / выбора файла */}
        <Paper
          variant="outlined"
          sx={{
            p: 2,
            textAlign: "center",
            borderColor: dragOver ? "primary.main" : "grey.400",
            backgroundColor: dragOver ? "grey.100" : "inherit",
            cursor: "pointer",
            transition: "border-color 0.3s, background-color 0.3s"
          }}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current.click()}
        >
          <Typography variant="body1">
            {file
              ? `${file.name} (${formatFileSize(file.size)})`
              : t("selectFile") ||
                "Select Video File (click or drag & drop)"}
          </Typography>
          <input
            ref={fileInputRef}
            type="file"
            hidden
            accept="video/*"
            onChange={handleFileChange}
          />
        </Paper>
        
        {/* Предупреждение о большом файле */}
        {uploadWarning && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            {uploadWarning}
          </Alert>
        )}
        
        <TextField
          label={t("videoName")}
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <TextField
          label={t("description")}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          multiline
          rows={3}
        />
        <Button 
          variant="contained" 
          type="submit"
          disabled={uploadInProgress.current || !file || !name}
        >
          {t("uploadVideo")}
        </Button>
      </Box>
      
      {/* Прогресс загрузки файла */}
      {uploadInProgress.current && uploadProgress > 0 && uploadProgress < 100 && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="body2" sx={{ mb: 1 }}>
            {t("uploadingFile", "Uploading file to server")}
          </Typography>
          <LinearProgress 
            variant="determinate" 
            value={uploadProgress} 
            sx={{
              height: 8,
              borderRadius: 4,
              backgroundColor: 'rgba(0, 0, 0, 0.1)',
              '& .MuiLinearProgress-bar': {
                borderRadius: 4,
                backgroundColor: 'primary.main',
              }
            }}
          />
          <Typography variant="caption" sx={{ mt: 0.5, display: 'block' }}>
            {uploadProgress}%
          </Typography>
        </Box>
      )}
      
      {/* Прогресс обработки видео */}
      {(taskId || (uploadInProgress.current && uploadProgress === 100)) && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="body2" sx={{ mb: 1 }}>
            {t("processingVideo", "Processing video")}
          </Typography>
          <LinearProgress 
            variant="determinate" 
            value={progress} 
            sx={{
              height: 10,
              borderRadius: 5,
              backgroundColor: 'rgba(0, 0, 0, 0.1)',
              '& .MuiLinearProgress-bar': {
                borderRadius: 5,
                backgroundColor: 'success.main',
              }
            }}
          />
          <Typography variant="body2" sx={{ mt: 1 }}>
            {t("status")}: {statusText} ({progress}%)
          </Typography>
        </Box>
      )}
      
      <AlertMessage
        open={!!error}
        onClose={() => setError("")}
        severity="error"
        message={error}
      />
    </Box>
  );
};

export default VideoUploadForm;
