import { Navigate, Route, Routes } from 'react-router-dom';

import ErrorBoundary from './components/ErrorBoundary.jsx';
import DashboardLayout from './components/Layout/DashboardLayout.jsx';
import ProtectedRoute from './components/ProtectedRoute.jsx';

import Login from './modules/Auth/Login.jsx';
import Register from './modules/Auth/Register.jsx';

import Dashboard from './modules/Dashboard/Dashboard.jsx';
import PatientList from './modules/Patients/PatientList.jsx';
import PatientForm from './modules/Patients/PatientForm.jsx';
import PatientDetail from './modules/Patients/PatientDetail.jsx';
import MRIResult from './modules/MRI/MRIResult.jsx';
import ECGResult from './modules/ECG/ECGResult.jsx';
import MRILanding from './modules/MRI/MRILanding.jsx';
import ECGLanding from './modules/ECG/ECGLanding.jsx';
import EEGLanding from './modules/EEG/EEGLanding.jsx';
import EEGResult from './modules/EEG/EEGResult.jsx';
import EchoLanding from './modules/Echo/EchoLanding.jsx';
import EchoResult from './modules/Echo/EchoResult.jsx';
import ReportList from './modules/Reports/ReportList.jsx';

export default function App() {
  return (
    <ErrorBoundary>
      <Routes>
        {/* public */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        {/* protected */}
        <Route
          element={
            <ProtectedRoute>
              <DashboardLayout />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<Dashboard />} />
          <Route path="/patients" element={<PatientList />} />
          <Route path="/patients/new" element={<PatientForm />} />
          <Route path="/patients/:id" element={<PatientDetail />} />
          <Route path="/patients/:id/edit" element={<PatientForm />} />
          <Route path="/mri" element={<MRILanding />} />
          <Route path="/mri/:id" element={<MRIResult />} />
          <Route path="/ecg" element={<ECGLanding />} />
          <Route path="/ecg/:id" element={<ECGResult />} />
          <Route path="/eeg" element={<EEGLanding />} />
          <Route path="/eeg/:id" element={<EEGResult />} />
          <Route path="/echo" element={<EchoLanding />} />
          <Route path="/echo/:id" element={<EchoResult />} />
          <Route path="/reports" element={<ReportList />} />
          <Route path="/reports/:patientId" element={<ReportList />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  );
}
