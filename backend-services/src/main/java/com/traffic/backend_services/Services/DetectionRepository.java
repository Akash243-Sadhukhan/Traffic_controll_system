package com.traffic.backend_services.Services;

import com.traffic.backend_services.Entity.Detection;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface DetectionRepository extends MongoRepository<Detection, String> {}
