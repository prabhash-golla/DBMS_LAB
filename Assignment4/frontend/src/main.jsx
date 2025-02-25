import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  // <StrictMode>
  <Router>
    <Routes>
      <Route exact path="/" element={<App />}/>
    </Routes>
  </Router>
  // </StrictMode>,
)
