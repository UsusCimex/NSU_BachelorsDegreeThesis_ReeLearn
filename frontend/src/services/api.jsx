import axios from "axios";

const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000/api/v1";

// Создаем особый экземпляр axios для загрузок с увеличенными таймаутами
const uploadClient = axios.create({
  timeout: 3600000, // 1 час для загрузки больших файлов
  maxContentLength: 15 * 1024 * 1024 * 1024, // 15 ГБ макс размер контента
  maxBodyLength: 15 * 1024 * 1024 * 1024 // 15 ГБ макс размер тела запроса
});

export const searchVideos = async (query, exact) => {
  try {
    const res = await axios.get(`${API_BASE}/search`, { params: { query, exact } });
    return res.data;
  } catch (error) {
    console.error("Search error:", error);
    throw error;
  }
};

export const uploadVideo = async (file, name, description, onProgress) => {
  const formData = new FormData();
  formData.append("video_file", file);
  formData.append("name", name);
  formData.append("description", description || "");
  
  try {
    const res = await uploadClient.post(`${API_BASE}/videos/upload`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
      // Добавляем обработку прогресса загрузки
      onUploadProgress: onProgress || ((progressEvent) => {
        const percentCompleted = Math.round(
          (progressEvent.loaded * 100) / progressEvent.total
        );
        console.log(`Upload progress: ${percentCompleted}%`);
      })
    });
    return res.data;
  } catch (error) {
    console.error("Upload error:", error);
    
    // Добавляем более подробную информацию об ошибке в консоль
    if (error.response) {
      console.error("Response error data:", error.response.data);
      console.error("Response error status:", error.response.status);
    } else if (error.request) {
      console.error("Request error:", error.request);
    }
    
    throw error;
  }
};

export const getVideoFragments = async (videoId) => {
  try {
    const res = await axios.get(`${API_BASE}/videos/${videoId}/fragments`);
    return res.data;
  } catch (error) {
    console.error("Get fragments error:", error);
    throw error;
  }
};

export const getVideos = async () => {
  try {
    const res = await axios.get(`${API_BASE}/videos`);
    return res.data;
  } catch (error) {
    console.error("Get videos error:", error);
    throw error;
  }
};

export const getTaskStatus = async (taskId) => {
  try {
    const res = await axios.get(`${API_BASE}/tasks/${taskId}`);
    return res.data;
  } catch (error) {
    console.error("Get task status error:", error);
    throw error;
  }
};

// Функция проверки сервера
/*export const checkServerHealth = async () => {
  try {
    const res = await axios.get(`${API_BASE.replace('/api/v1', '')}/health`);
    return res.data;
  } catch (error) {
    console.error("Server health check error:", error);
    // Если сервер вернул ошибку с деталями, возвращаем их
    if (error.response && error.response.data) {
      return error.response.data;
    }
    throw error;
  }
};

export const cleanupTempFiles = async (force = false, hours = 12) => {
  try {
    const res = await axios.post(`${API_BASE}/videos/cleanup-temp`, null, {
      params: { force, hours }
    });
    return res.data;
  } catch (error) {
    console.error("Cleanup temp files error:", error);
    throw error;
  }
};*/
