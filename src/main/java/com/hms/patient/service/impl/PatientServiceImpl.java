package com.hms.patient.service.impl;

import com.hms.exception.BusinessValidationException;
import com.hms.exception.ResourceNotFoundException;
import com.hms.patient.dto.PatientRequest;
import com.hms.patient.dto.PatientResponse;
import com.hms.patient.entity.Patient;
import com.hms.patient.mapper.PatientMapper;
import com.hms.patient.repository.PatientRepository;
import com.hms.patient.service.PatientService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.concurrent.atomic.AtomicLong;

@Slf4j
@Service
@RequiredArgsConstructor
public class PatientServiceImpl implements PatientService {

    private final PatientRepository patientRepository;
    private final PatientMapper patientMapper;

    private static final AtomicLong patientCounter = new AtomicLong(0);

    @Override
    @Transactional
    public PatientResponse createPatient(PatientRequest request) {
        log.info("Creating new patient with phone: [REDACTED]"); // Phone is PII - not logged per security policy

        if (request.getEmail() != null && patientRepository.existsByEmail(request.getEmail())) {
            throw new BusinessValidationException("Patient with email '" + request.getEmail() + "' already exists");
        }
        if (patientRepository.existsByPhone(request.getPhone())) {
            throw new BusinessValidationException("Patient with phone '" + request.getPhone() + "' already exists");
        }

        Patient patient = patientMapper.toEntity(request);
        patient.setPatientCode(generatePatientCode());

        Patient saved = patientRepository.save(patient);
        log.info("Patient created successfully with code: {}", saved.getPatientCode());
        return patientMapper.toResponse(saved);
    }

    @Override
    @Transactional(readOnly = true)
    public PatientResponse getPatientById(Long id) {
        Patient patient = findPatientById(id);
        return patientMapper.toResponse(patient);
    }

    @Override
    @Transactional(readOnly = true)
    public PatientResponse getPatientByCode(String patientCode) {
        Patient patient = patientRepository.findByPatientCode(patientCode)
                .orElseThrow(() -> new ResourceNotFoundException("Patient", "patientCode", patientCode));
        return patientMapper.toResponse(patient);
    }

    @Override
    @Transactional(readOnly = true)
    public Page<PatientResponse> getAllPatients(Pageable pageable) {
        return patientRepository.findByActiveTrue(pageable).map(patientMapper::toResponse);
    }

    @Override
    @Transactional(readOnly = true)
    public Page<PatientResponse> searchPatients(String search, Pageable pageable) {
        return patientRepository.searchPatients(search, pageable).map(patientMapper::toResponse);
    }

    @Override
    @Transactional
    public PatientResponse updatePatient(Long id, PatientRequest request) {
        log.info("Updating patient with id: {}", id);
        Patient patient = findPatientById(id);

        if (request.getEmail() != null && !request.getEmail().equals(patient.getEmail())
                && patientRepository.existsByEmail(request.getEmail())) {
            throw new BusinessValidationException("Email '" + request.getEmail() + "' is already in use");
        }
        if (!request.getPhone().equals(patient.getPhone())
                && patientRepository.existsByPhone(request.getPhone())) {
            throw new BusinessValidationException("Phone '" + request.getPhone() + "' is already in use");
        }

        patientMapper.updateEntityFromRequest(request, patient);
        Patient updated = patientRepository.save(patient);
        log.info("Patient updated successfully: {}", updated.getPatientCode());
        return patientMapper.toResponse(updated);
    }

    @Override
    @Transactional
    public void deactivatePatient(Long id) {
        log.info("Deactivating patient with id: {}", id);
        Patient patient = findPatientById(id);
        patient.setActive(false);
        patientRepository.save(patient);
        log.info("Patient deactivated: {}", patient.getPatientCode());
    }

    private Patient findPatientById(Long id) {
        return patientRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Patient", "id", id));
    }

    private String generatePatientCode() {
        String datePart = LocalDate.now().format(DateTimeFormatter.ofPattern("yyyyMM"));
        long count = patientRepository.count() + 1;
        return String.format("PAT-%s-%04d", datePart, count);
    }
}
